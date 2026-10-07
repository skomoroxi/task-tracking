#!/usr/bin/env python3
"""Nightly sync: monday.com "Часы факт" -> Google Sheet, columns F (hours) and G (monday_item_id).

Implements nightly-sync-algorithm.md (version 2).

    python sync.py --dry-run            # read everything, print the plan and the report
    python sync.py --apply              # same, then write columns F/G in one batch

Every run also writes logs/log-YYYY-MM-DD_HH-MM-SS.log: the cells actually written and the errors.

Environment:
    MONDAY_TOKEN     monday.com API token (read-only use: the script never sends mutations)
    GOOGLE_SA_JSON   service-account JSON (the JSON text itself or a path to the file)
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import sys
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import yaml

MONDAY_URL = "https://api.monday.com/v2"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# --------------------------------------------------------------------------------------
# Small parsers
# --------------------------------------------------------------------------------------

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}|\d{2}))?")
_GROUP_RE = re.compile(r"^\s*Спринт\s*(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\s*-", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def parse_group_start(title: str) -> Optional[dt.date]:
    """Start date of a monday sprint group, or None if the group is not a sprint group.
    Only the start date is used: end dates contain typos."""
    m = _GROUP_RE.match(title or "")
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def parse_sheet_sprint(text: str, anchors: list[dt.date]) -> Optional[dt.date]:
    """Start date of a sheet 'Спринт' value such as '31.08 - 06.09' or '28.09.2026 - 04.10.2026'.
    A missing year is taken so the date lands nearest to a monday group start (anchors)."""
    if not text:
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    if m.group(3):
        y = int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    ref = anchors or [dt.date.today()]
    best = None
    for year in {a.year + k for a in ref for k in (-1, 0, 1)}:
        try:
            cand = dt.date(year, mo, d)
        except ValueError:
            continue
        dist = min(abs((cand - a).days) for a in ref)
        if best is None or dist < best[0]:
            best = (dist, cand)
    return best[1] if best else None


def looks_like_sprint(text: str) -> bool:
    return bool(text) and bool(re.search(r"\d{1,2}\.\d{1,2}", text))


def parse_hours(text) -> Optional[float]:
    """'' -> None (no data); '0' -> 0.0 (a real value); '.5' / '0,5' -> 0.5."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace(",", ".").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_hours(v: Optional[float]):
    if v is None:
        return ""
    v = round(v, 4)
    return int(v) if v == int(v) else v


def col_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def quote_tab(tab: str) -> str:
    return "'" + tab.replace("'", "''") + "'"


# --------------------------------------------------------------------------------------
# Name normalization (algorithm 4.4)
# --------------------------------------------------------------------------------------

_DASHES = "—–‒‑‐"


def project_tokens(tab: str) -> list[str]:
    t = tab.lower().strip()
    toks = {t}
    if "." in t:
        toks.add(t.rsplit(".", 1)[0])
    return sorted(toks, key=len, reverse=True)


def normalize_name(name: str, tab: str) -> str:
    s = (name or "").lower().replace("ё", "е")
    for ch in _DASHES:
        s = s.replace(ch, "-")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("(copy)", " ")
    # UPD markers: "UPD:2", "UPD2:", "UPD:", "UPD1:"
    s = re.sub(r"\bupd\s*:?\s*\d*\s*:?", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for tok in project_tokens(tab):
        e = re.escape(tok)
        s = re.sub(rf"^{e}\s*[-:|]\s*", "", s)
        s = re.sub(rf"\s*[-:|]\s*{e}$", "", s)
    # quantity suffixes: "x2", "х3", "- 6 шт"
    s = re.sub(r"\s+[xх]\s*\d+$", "", s)
    s = re.sub(r"\s*-?\s*\d+\s*шт\.?$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -:")
    return s


def url_key(name: str) -> Optional[str]:
    """If a name contains a URL, the URL (without scheme/trailing slash) is the match key.
    An exact URL is safer than a name, so 'Обновление статьи <url>' matches 'Обновление <url>'."""
    m = _URL_RE.search(name or "")
    if not m:
        return None
    u = m.group(0).lower().rstrip("/.,)")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return "url:" + u


def match_key(name: str, tab: str) -> str:
    return url_key(name) or normalize_name(name, tab)


# --------------------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------------------


@dataclass
class Item:
    id: str
    name: str
    hours: Optional[float]
    tags: list[str]
    tabs: set[str]
    report_only: bool
    start: dt.date
    deadline: Optional[str]
    board_id: int
    owner: str
    claimed_tabs: set[str] = field(default_factory=set)


@dataclass
class Row:
    tab: str
    row: int                # 1-based sheet row
    name: str
    specialist: str
    sprint_text: str
    sprint: Optional[dt.date]
    f_raw: str
    g_raw: str
    ids: list[str] = field(default_factory=list)
    matched: list[Item] = field(default_factory=list)
    stale: bool = False
    status: str = ""        # why it was matched / not matched


@dataclass
class TabData:
    title: str
    rows: list[Row]
    f_col: int
    g_col: int
    g_header_missing: bool


@dataclass
class Board:
    id: int
    owner: str
    window: list[dt.date]                 # start dates of the groups read, newest first
    items: list[Item]
    error: str = ""


@dataclass
class Report:
    started: str = ""
    f_changes: list[tuple] = field(default_factory=list)   # (tab,row,name,sprint,old,new)
    g_changes: int = 0
    stale: list[tuple] = field(default_factory=list)       # (tab,row,name,old ids)
    reset_tabs: list[str] = field(default_factory=list)
    unmatched_items: list[Item] = field(default_factory=list)
    unmatched_rows: list[tuple] = field(default_factory=list)  # (tab,row,name,sprint,reason)
    multi_tab_items: list[Item] = field(default_factory=list)
    skipped_tabs: list[tuple] = field(default_factory=list)
    no_board: dict = field(default_factory=lambda: defaultdict(int))
    board_errors: list[tuple] = field(default_factory=list)
    alias_suggestions: set = field(default_factory=set)
    concurrent_skips: list[tuple] = field(default_factory=list)
    big_overwrites: list[tuple] = field(default_factory=list)  # f_changes entries that trip the overwrite check
    written_cells: list[tuple] = field(default_factory=list)  # (tab,a1,old,new), only after a successful write
    stopped: str = ""
    written: bool = False


# --------------------------------------------------------------------------------------
# monday.com (read-only)
# --------------------------------------------------------------------------------------


class MondayReader:
    def __init__(self, token: str):
        import requests
        self.s = requests.Session()
        self.s.headers.update({"Authorization": token, "Content-Type": "application/json"})

    def query(self, q: str, variables: dict | None = None) -> dict:
        # Hard rule 1: queries only, never mutations.
        if re.search(r"\bmutation\b", q, re.IGNORECASE):
            raise RuntimeError("Refusing to send a mutation to monday.com (read-only sync)")
        r = self.s.post(MONDAY_URL, json={"query": q, "variables": variables or {}}, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(f"monday.com error: {data['errors']}")
        return data["data"]

    def board_meta(self, board_id: int) -> dict:
        d = self.query(
            "query($b:[ID!]){boards(ids:$b){id name columns{id title type} groups{id title position}}}",
            {"b": [str(board_id)]},
        )
        if not d["boards"]:
            raise RuntimeError("board not found or no access")
        return d["boards"][0]

    def group_items(self, board_id: int, group_id: str, col_ids: list[str]) -> list[dict]:
        cols = json.dumps(col_ids)
        d = self.query(
            "query($b:[ID!],$g:[String]){boards(ids:$b){groups(ids:$g){items_page(limit:200){cursor "
            "items{id name column_values(ids:%s){id text}}}}}}" % cols,
            {"b": [str(board_id)], "g": [group_id]},
        )
        page = d["boards"][0]["groups"][0]["items_page"]
        items, cursor = list(page["items"]), page["cursor"]
        while cursor:
            d = self.query(
                "query($c:String!){next_items_page(limit:200,cursor:$c){cursor "
                "items{id name column_values(ids:%s){id text}}}}" % cols,
                {"c": cursor},
            )
            items += d["next_items_page"]["items"]
            cursor = d["next_items_page"]["cursor"]
        return items


def find_col(columns: list[dict], title: str) -> Optional[str]:
    t = title.strip().lower()
    for c in columns:
        if (c.get("title") or "").strip().lower() == t:
            return c["id"]
    return None


def find_deadline_col(columns: list[dict]) -> Optional[str]:
    dates = [c for c in columns if c.get("type") == "date"]
    for c in dates:
        if re.search(r"дедлайн|deadline|срок", c.get("title") or "", re.IGNORECASE):
            return c["id"]
    return dates[0]["id"] if dates else None


def load_board(reader, board_id: int, owner: str, cfg: dict) -> Board:
    meta = reader.board_meta(board_id)
    cols = meta["columns"]
    hours_col = find_col(cols, cfg["columns"]["monday_hours"])
    tags_col = find_col(cols, cfg["columns"]["monday_tags"])
    if not hours_col or not tags_col:
        return Board(board_id, owner, [], [], error=f"columns '{cfg['columns']['monday_hours']}'/"
                     f"'{cfg['columns']['monday_tags']}' not found")
    dl_col = find_deadline_col(cols)
    groups = sorted(meta["groups"], key=lambda g: float(g.get("position") or 0))
    sprint_groups = [(g, parse_group_start(g["title"])) for g in groups]
    sprint_groups = [(g, s) for g, s in sprint_groups if s][: cfg["groups_limit"]]
    items = []
    for g, start in sprint_groups:
        want = [c for c in (hours_col, tags_col, dl_col) if c]
        for it in reader.group_items(board_id, g["id"], want):
            vals = {cv["id"]: cv.get("text") or "" for cv in it["column_values"]}
            tags = [t.strip() for t in vals.get(tags_col, "").split(",") if t.strip()]
            items.append(Item(
                id=str(it["id"]), name=it["name"], hours=parse_hours(vals.get(hours_col)),
                tags=tags, tabs=set(), report_only=False, start=start,
                deadline=vals.get(dl_col) or None, board_id=board_id, owner=owner,
            ))
    return Board(board_id, owner, [s for _, s in sprint_groups], items)


# --------------------------------------------------------------------------------------
# Google Sheets
# --------------------------------------------------------------------------------------


class SheetsClient:
    def __init__(self, sa_json: str, spreadsheet_id: str):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        info = json.loads(open(sa_json).read()) if os.path.exists(sa_json) else json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        self.api = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
        self.id = spreadsheet_id

    def tab_titles(self) -> list[str]:
        meta = self.api.get(spreadsheetId=self.id, fields="sheets.properties.title").execute()
        return [s["properties"]["title"] for s in meta["sheets"]]

    def read(self, ranges: list[str]) -> list[list[list[str]]]:
        res = self.api.values().batchGet(spreadsheetId=self.id, ranges=ranges,
                                         valueRenderOption="FORMATTED_VALUE").execute()
        return [vr.get("values", []) for vr in res.get("valueRanges", [])]

    def write(self, data: list[dict]) -> None:
        # Hard rule 3: callers only ever pass single cells in columns F/G.
        self.api.values().batchUpdate(spreadsheetId=self.id, body={
            "valueInputOption": "RAW", "data": data}).execute()


def parse_tab(title: str, values: list[list[str]], cfg: dict, anchors: list[dt.date]):
    """Returns (TabData, None) or (None, reason_to_skip)."""
    if not values:
        return None, "empty tab"
    header = [str(h).strip().lower() for h in values[0]]
    c = cfg["columns"]

    def idx(name):
        n = name.strip().lower()
        return header.index(n) if n in header else None

    i_spec, i_sprint, i_f = idx(c["sheet_specialist"]), idx(c["sheet_sprint"]), idx(c["sheet_hours"])
    if i_spec is None or i_sprint is None or i_f is None:
        return None, "headers 'Спец' / 'Спринт' / 'Часы факт' not found in row 1"
    if any("#REF!" in str(r[0]) for r in values[1:] if r):
        return None, "column A contains #REF!"
    i_g = idx(c["sheet_item_id"])
    g_missing = i_g is None
    if g_missing:
        i_g = i_f + 1
        if len(values[0]) > i_g and str(values[0][i_g]).strip():
            return None, f"column {col_letter(i_g)} is occupied, can't add 'monday_item_id'"
    sprints = [r[i_sprint] for r in values[1:] if len(r) > i_sprint and str(r[i_sprint]).strip()]
    if sprints and sum(looks_like_sprint(s) for s in sprints) < len(sprints) / 2:
        return None, "'Спринт' column holds numbers, not date ranges"

    def cell(r, i):
        return str(r[i]).strip() if len(r) > i and r[i] is not None else ""

    rows = []
    for n, r in enumerate(values[1:], start=2):
        name = cell(r, 0)
        if not name:
            continue
        filled = [cell(r, i) for i in range(1, max(len(r), 1))]
        if not any(filled):
            continue                      # section row such as "Сателлиты"
        g = cell(r, i_g)
        rows.append(Row(
            tab=title, row=n, name=name, specialist=cell(r, i_spec), sprint_text=cell(r, i_sprint),
            sprint=parse_sheet_sprint(cell(r, i_sprint), anchors), f_raw=cell(r, i_f), g_raw=g,
            ids=[x.strip() for x in g.split(",") if x.strip()],
        ))
    return TabData(title, rows, i_f, i_g, g_missing), None


# --------------------------------------------------------------------------------------
# Matching (algorithm sections 2 and 4)
# --------------------------------------------------------------------------------------


def assign_tabs(items: list[Item], tab_titles: set[str], cfg: dict, report: Report) -> None:
    ignored = {t.lower() for t in cfg["ignored_tags"]}
    report_only = {t.lower() for t in cfg["report_only_tags"]}
    aliases = {k.lower(): v for k, v in (cfg.get("tag_aliases") or {}).items()}
    lower_tabs = {t.lower(): t for t in tab_titles}
    for it in items:
        for tag in it.tags:
            tl = tag.lower()
            if tl in ignored:
                continue
            if tl in report_only:
                it.report_only = True
                continue
            if tl in aliases:
                it.tabs.add(aliases[tl])
            elif tl in lower_tabs:
                it.tabs.add(lower_tabs[tl])
            elif "." in tl:
                report.alias_suggestions.add(tag)   # looks like a project, no tab with that name


def item_sort_key(it: Item):
    return (it.deadline or "9999-99-99", int(it.id) if it.id.isdigit() else 0)


def plan_tab(tab: TabData, boards: dict[str, Board], cfg: dict, report: Report):
    """Decide the F/G value of every row of one tab. Returns list of (row, new_f, new_g) or
    None when reset detection blocks the tab."""
    generic = {normalize_name(g, tab.title): normalize_name(g, tab.title).split(" ")[0]
               for g in cfg["generic_names"]}
    items_by_id = {it.id: it for b in boards.values() for it in b.items}
    claimed: set[str] = set()

    in_window: list[Row] = []
    for r in tab.rows:
        board = boards.get(r.specialist)
        if board is None:
            if r.specialist:
                report.no_board[r.specialist] += 1
            r.status = "no board"
            continue
        if board.error or not board.window:
            r.status = "board unreadable"
            continue
        if r.sprint is None:
            r.status = "no sprint date"
            continue
        if r.sprint < min(board.window):
            r.status = "older than window"      # frozen: never touched
            continue
        in_window.append(r)

    # ---- 2.2 / 4.2: rows with IDs in G
    with_ids = [r for r in in_window if r.ids]
    for r in with_ids:
        board = boards[r.specialist]
        its = [items_by_id.get(i) for i in r.ids]
        ok = all(
            it is not None and it.board_id == board.id and it.start == r.sprint and tab.title in it.tabs
            for it in its
        )
        if ok:
            r.matched = its
            r.status = "matched by id"
            claimed.update(r.ids)
        else:
            r.stale = True
    stale = [r for r in with_ids if r.stale]
    if with_ids and len(stale) / len(with_ids) > cfg["reset_threshold"]:
        report.reset_tabs.append(tab.title)
        return None
    for r in stale:
        report.stale.append((tab.title, r.row, r.name, r.g_raw))

    # ---- 4.3 / 4.4: name matching for rows without a valid ID
    todo = []
    for r in in_window:
        if r.matched:
            continue
        board = boards[r.specialist]
        if r.sprint > max(board.window):
            r.status = "future sprint"          # silent
            continue
        if r.sprint not in board.window:
            r.status = "no sprint group"
            report.unmatched_rows.append((tab.title, r.row, r.name, r.sprint_text,
                                          f"no sprint group on {board.owner}'s board"))
            continue
        todo.append(r)

    def pool(board: Board, sprint):
        return [it for it in board.items if it.start == sprint and tab.title in it.tabs
                and it.id not in claimed]

    rows_by = defaultdict(list)
    for r in todo:
        rows_by[(r.specialist, r.sprint, match_key(r.name, tab.title))].append(r)
    for (spec, sprint, key), rows in rows_by.items():
        cands = [it for it in pool(boards[spec], sprint) if match_key(it.name, tab.title) == key]
        if not cands:
            continue
        cands.sort(key=item_sort_key)
        if len(rows) == 1:
            rows[0].matched = cands
            rows[0].status = "matched by name" + (" (sum)" if len(cands) > 1 else "")
            claimed.update(it.id for it in cands)
        elif len(rows) == len(cands):
            for r, it in zip(rows, cands):
                r.matched = [it]
                r.status = "matched by name (paired by deadline)"
                claimed.add(it.id)
        else:
            for r in rows:
                r.status = "count mismatch"
                report.unmatched_rows.append((tab.title, r.row, r.name, r.sprint_text,
                                              f"count mismatch: {len(rows)} rows vs {len(cands)} items"))

    # ---- 4.5 generic names
    gen_by = defaultdict(list)
    for r in todo:
        if r.matched or r.status:
            continue
        g = normalize_name(r.name, tab.title)
        if g in generic:
            gen_by[(r.specialist, r.sprint, g)].append(r)
    for (spec, sprint, g), rows in gen_by.items():
        first = generic[g]
        cands = sorted([it for it in pool(boards[spec], sprint)
                        if normalize_name(it.name, tab.title).startswith(first)], key=item_sort_key)
        if cands and len(cands) == len(rows):
            for r, it in zip(rows, cands):
                r.matched = [it]
                r.status = "generic name, paired by deadline"
                claimed.add(it.id)
        else:
            for r in rows:
                r.status = "generic count mismatch"
                report.unmatched_rows.append((tab.title, r.row, r.name, r.sprint_text,
                                              f"generic name: {len(rows)} rows vs {len(cands)} "
                                              f"'{first}…' items"))

    # ---- remaining rows: near-match report
    for r in todo:
        if r.matched or r.status:
            continue
        r.status = "no match"
        left = pool(boards[r.specialist], r.sprint)
        nk = normalize_name(r.name, tab.title)
        best = max(left, key=lambda it: difflib.SequenceMatcher(
            None, nk, normalize_name(it.name, tab.title)).ratio(), default=None)
        if best is not None:
            ratio = difflib.SequenceMatcher(None, nk, normalize_name(best.name, tab.title)).ratio()
            if ratio >= 0.5:
                report.unmatched_rows.append((tab.title, r.row, r.name, r.sprint_text,
                                              f"near-match: '{best.name}' ({fmt_hours(best.hours) if best.hours is not None else '—'} h)"))
                continue
        report.unmatched_rows.append((tab.title, r.row, r.name, r.sprint_text, "no monday item"))

    for it in items_by_id.values():
        if it.id in claimed:
            it.claimed_tabs.add(tab.title)

    # ---- section 5: decide values
    plan = []
    for r in tab.rows:
        new_f, new_g = r.f_raw, r.g_raw
        if r.matched:
            hrs = [it.hours for it in r.matched if it.hours is not None]
            total = sum(hrs) if hrs else None
            ids = ",".join(it.id for it in r.matched)
            if r.stale:
                new_f = ""
            if total is not None and parse_hours(new_f) != round(total, 4):
                new_f = fmt_hours(total)
            new_g = ids
        elif r.stale:
            new_f, new_g = "", ""
        plan.append((r, new_f, new_g))
    return plan


# --------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------


def find_big_overwrites(report: Report, ratio: float) -> list[tuple]:
    """F changes that replace a filled number with a very different one (more than `ratio` times
    bigger or smaller) or with nothing. Rows whose stale ID was just cleared are expected to change."""
    stale_rows = {(t, n) for t, n, *_ in report.stale}
    out = []
    for ch in report.f_changes:
        t, n, _, _, old, new = ch
        o = parse_hours(old)
        if o is None or (t, n) in stale_rows:
            continue
        nv = parse_hours(new)
        if nv is None:
            out.append(ch)
            continue
        lo, hi = sorted((abs(o), abs(nv)))
        if hi > 0 and (lo == 0 or hi / lo > ratio):
            out.append(ch)
    return out


def run(cfg: dict, sheets, reader, apply: bool, only_tabs: list[str] | None = None) -> Report:
    report = Report(started=dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    all_titles = sheets.tab_titles()
    wanted = only_tabs or cfg.get("tabs") or all_titles
    titles = [t for t in all_titles if t in wanted]
    for t in wanted:
        if t not in all_titles:
            report.skipped_tabs.append((t, "no tab with this name"))

    raw = sheets.read([f"{quote_tab(t)}!A1:Z" for t in titles])

    # boards for specialists that appear in these tabs
    specs = set()
    for vals in raw:
        hdr = [str(h).strip().lower() for h in (vals[0] if vals else [])]
        if cfg["columns"]["sheet_specialist"].lower() in hdr:
            i = hdr.index(cfg["columns"]["sheet_specialist"].lower())
            specs.update(str(r[i]).strip() for r in vals[1:] if len(r) > i and str(r[i]).strip())
    boards: dict[str, Board] = {}
    for spec in sorted(specs):
        bid = (cfg.get("specialists") or {}).get(spec)
        if not bid:
            continue
        try:
            boards[spec] = load_board(reader, int(bid), spec, cfg)
        except Exception as e:  # keep going with the other boards
            boards[spec] = Board(int(bid), spec, [], [], error=str(e))
        if boards[spec].error:
            report.board_errors.append((spec, boards[spec].error))
    all_items = [it for b in boards.values() for it in b.items]
    assign_tabs(all_items, set(all_titles), cfg, report)
    anchors = sorted({s for b in boards.values() for s in b.window})

    tabs: list[TabData] = []
    for t, vals in zip(titles, raw):
        td, why = parse_tab(t, vals, cfg, anchors)
        if why:
            report.skipped_tabs.append((t, why))
        else:
            tabs.append(td)

    writes: dict[tuple, object] = {}   # (tab, row, col) -> value
    expected: dict[tuple, str] = {}    # the value read, for the concurrency check
    for td in tabs:
        plan = plan_tab(td, boards, cfg, report)
        if plan is None:
            continue
        if td.g_header_missing and any(str(g) != r.g_raw for r, _, g in plan):
            writes[(td.title, 1, td.g_col)] = cfg["columns"]["sheet_item_id"]
            expected[(td.title, 1, td.g_col)] = ""
        for r, new_f, new_g in plan:
            if str(new_f) != r.f_raw:
                writes[(td.title, r.row, td.f_col)] = new_f
                expected[(td.title, r.row, td.f_col)] = r.f_raw
                report.f_changes.append((td.title, r.row, r.name, r.sprint_text, r.f_raw, new_f))
            if str(new_g) != r.g_raw:
                writes[(td.title, r.row, td.g_col)] = new_g
                expected[(td.title, r.row, td.g_col)] = r.g_raw
                report.g_changes += 1

    # items: unmatched with hours, and counted in two tabs
    tab_names = {td.title for td in tabs}
    for spec, b in boards.items():
        for it in b.items:
            relevant = it.tabs & tab_names
            if len(it.claimed_tabs) > 1:
                report.multi_tab_items.append(it)
            if it.hours is not None and ((relevant - it.claimed_tabs) or it.report_only):
                report.unmatched_items.append(it)

    # safety stop
    report.big_overwrites = find_big_overwrites(report, cfg.get("max_overwrite_ratio", 3))
    if report.reset_tabs:
        report.stopped = "reset detection fired on: " + ", ".join(report.reset_tabs)
    elif len(report.f_changes) > cfg["max_f_changes"]:
        report.stopped = f"{len(report.f_changes)} F cells would change (limit {cfg['max_f_changes']})"
    elif report.big_overwrites:
        report.stopped = (f"{len(report.big_overwrites)} filled F cells would change more than "
                          f"{cfg.get('max_overwrite_ratio', 3)}x or become empty")
    elif report.board_errors:
        report.stopped = "could not read board(s): " + ", ".join(s for s, _ in report.board_errors)

    if apply and not report.stopped and writes:
        # re-read F:G of affected tabs and skip cells changed since the first read
        aff = sorted({k[0] for k in writes})
        cols = {td.title: (td.f_col, td.g_col) for td in tabs}
        again = sheets.read([f"{quote_tab(t)}!A1:Z" for t in aff])
        now = {}
        for t, vals in zip(aff, again):
            for n, r in enumerate(vals, start=1):
                for c in cols[t]:
                    now[(t, n, c)] = str(r[c]).strip() if len(r) > c and r[c] is not None else ""
        data, cells = [], []
        for k, v in writes.items():
            assert k[2] in cols[k[0]], "refusing to write outside columns F/G"
            if now.get(k, "") != expected[k]:
                report.concurrent_skips.append(k)
                continue
            a1 = f"{col_letter(k[2])}{k[1]}"
            data.append({"range": f"{quote_tab(k[0])}!{a1}", "values": [[v]]})
            cells.append((k[0], a1, expected[k], v))
        if data:
            sheets.write(data)
            report.written_cells += cells
        report.written = True
    return report


def render_report(rep: Report, apply: bool) -> str:
    L = []
    mode = "APPLY" if apply else "DRY RUN"
    L.append(f"# Sync report — {rep.started} ({mode})\n")
    if rep.stopped:
        L.append(f"**SAFETY STOP — nothing written:** {rep.stopped}\n")
    elif apply:
        L.append("Changes were written to the sheet.\n" if rep.written else "Nothing to write.\n")
    L.append(f"F cells changed: **{len(rep.f_changes)}**, G cells changed: **{rep.g_changes}**\n")
    if rep.f_changes:
        L.append("| Tab | Row | Task | Sprint | Old F → New F |\n|---|---|---|---|---|")
        for t, n, name, sp, old, new in rep.f_changes:
            L.append(f"| {t} | {n} | {name[:70]} | {sp} | {old or '∅'} → {new if new != '' else '∅'} |")
        L.append("")
    if rep.big_overwrites:
        L.append("## Filled F cells that would change a lot (stopped the run — check them by hand)")
        L += [f"- {t} row {n}: {name[:60]} · {sp} · {old} → {new if new != '' else '∅'}"
              for t, n, name, sp, old, new in rep.big_overwrites] + [""]
    if rep.concurrent_skips:
        L.append("## Skipped: cell changed during the run")
        L += [f"- {t} {col_letter(c)}{n}" for t, n, c in rep.concurrent_skips] + [""]
    if rep.reset_tabs:
        L.append("## Task list changed, column G looks stale — clear F and G on these tabs")
        L += [f"- {t}" for t in rep.reset_tabs] + [""]
    if rep.stale:
        L.append("## Stale IDs cleared and re-matched")
        L += [f"- {t} row {n}: {name[:60]} (was {ids})" for t, n, name, ids in rep.stale] + [""]
    if rep.unmatched_rows:
        L.append("## Rows in the 8-sprint window without a match")
        L.append("| Tab | Row | Task | Sprint | Reason |\n|---|---|---|---|---|")
        for t, n, name, sp, why in rep.unmatched_rows:
            L.append(f"| {t} | {n} | {name[:70]} | {sp} | {why} |")
        L.append("")
    if rep.unmatched_items:
        L.append("## monday items with hours but no matching row")
        for it in sorted(rep.unmatched_items, key=lambda i: (i.owner, i.start)):
            tabs = ", ".join(sorted(it.tabs)) or ", ".join(it.tags)
            L.append(f"- {it.owner} · {it.start:%d.%m} · {it.name[:70]} · {fmt_hours(it.hours)} h · {tabs}")
        L.append("")
    if rep.multi_tab_items:
        L.append("## Items counted in two or more tabs")
        L += [f"- {it.owner} · {it.name[:70]} · {', '.join(sorted(it.claimed_tabs))}"
              for it in rep.multi_tab_items] + [""]
    if rep.skipped_tabs:
        L.append("## Skipped tabs")
        L += [f"- {t}: {why}" for t, why in rep.skipped_tabs] + [""]
    if rep.no_board:
        L.append("## Specialists without a board in config.yaml")
        L += [f"- {s}: {n} rows" for s, n in sorted(rep.no_board.items())] + [""]
    if rep.board_errors:
        L.append("## Boards that could not be read")
        L += [f"- {s}: {e}" for s, e in rep.board_errors] + [""]
    if rep.alias_suggestions:
        L.append("## Suggested tag_aliases for config.yaml (tags with no tab of the same name)")
        L += [f"- {t}" for t in sorted(rep.alias_suggestions)] + [""]
    return "\n".join(L)


def log_name(now: dt.datetime) -> str:
    # No ':' in the time: it is not allowed in file names on Windows and breaks git checkouts there.
    return f"log-{now:%Y-%m-%d_%H-%M-%S}.log"


def render_log(now: dt.datetime, apply: bool, rep: Optional[Report], error: str = "") -> str:
    """Plain-text run log: the cells actually written and everything that went wrong."""
    mode = "APPLY" if apply else "DRY RUN"
    L = [f"Sync log {now:%Y-%m-%d %H:%M:%S} ({mode})"]
    if error:
        L.append("Result: FAILED, nothing was written")
    elif rep.stopped:
        L.append(f"Result: SAFETY STOP, nothing was written: {rep.stopped}")
    elif not apply:
        L.append(f"Result: dry run, nothing was written ({len(rep.f_changes)} F / {rep.g_changes} G cells would change)")
    else:
        L.append(f"Result: OK, {len(rep.written_cells)} cells written")

    cells = rep.written_cells if rep else []
    L += ["", f"== Updated cells ({len(cells)}) =="]
    L += [f"{t}!{a1}: {old or '(empty)'} -> {new if new != '' else '(empty)'}" for t, a1, old, new in cells]

    errs = []
    if error:
        errs.append(error.rstrip())
    if rep:
        if rep.stopped:
            errs.append(f"Safety stop: {rep.stopped}")
        errs += [f"Big overwrite, not written: {t}!row {n} ({name[:60]}): {old} -> {new if new != '' else '(empty)'}"
                 for t, n, name, _, old, new in rep.big_overwrites]
        errs += [f"Board not read: {s}: {e}" for s, e in rep.board_errors]
        errs += [f"Not written, cell changed during the run: {t}!{col_letter(c)}{n}"
                 for t, n, c in rep.concurrent_skips]
        errs += [f"Tab not written, column G looks stale (task list changed): {t}" for t in rep.reset_tabs]
        errs += [f"Tab skipped: {t}: {why}" for t, why in rep.skipped_tabs]
    L += ["", f"== Errors ({len(errs)}) =="] + errs
    return "\n".join(L) + "\n"


def write_log(log_dir: str, now: dt.datetime, text: str) -> str:
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, log_name(now))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--config", default=os.path.join(here, "config.yaml"))
    ap.add_argument("--tabs", help="comma-separated tab names (overrides config)")
    ap.add_argument("--report", help="also save the report to this file")
    ap.add_argument("--log-dir", default=os.path.join(here, "logs"), help="folder for log-<date_time>.log")
    a = ap.parse_args(argv)

    now = dt.datetime.now()
    token, sa = os.environ.get("MONDAY_TOKEN"), os.environ.get("GOOGLE_SA_JSON")
    if not token or not sa:
        print("Set MONDAY_TOKEN and GOOGLE_SA_JSON", file=sys.stderr)
        write_log(a.log_dir, now, render_log(now, a.apply, None, "Set MONDAY_TOKEN and GOOGLE_SA_JSON"))
        return 2
    try:
        cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
        rep = run(cfg, SheetsClient(sa, cfg["spreadsheet_id"]), MondayReader(token), a.apply,
                  [t.strip() for t in a.tabs.split(",")] if a.tabs else None)
    except Exception:
        path = write_log(a.log_dir, now, render_log(now, a.apply, None, traceback.format_exc()))
        print(f"Log: {path}", file=sys.stderr)
        raise
    text = render_report(rep, a.apply)
    print(text)
    if a.report:
        os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
        open(a.report, "w", encoding="utf-8").write(text)
    path = write_log(a.log_dir, now, render_log(now, a.apply, rep))
    print(f"Log: {path}", file=sys.stderr)
    return 1 if rep.stopped else 0


if __name__ == "__main__":
    sys.exit(main())
