"""Offline tests: data copied from the real sheet and boards on 30.09.2026.
The expected results equal the manual run described in the conversation that day."""
import datetime as dt
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sync  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config.yaml"), encoding="utf-8"))
H = ["Название задачи", "Спец", "Спринт", "Статус", "Часы план", "Часы факт"]
D, A, Y = "Дубинко Денис", "Панина Аня", "Сухенко Юрий"
S28, S05, S19 = "28.09.2026 - 04.10.2026", "05.10.2026 - 11.10.2026", "19.10.2026 -25.10.2026"


def sheet_data():
    return {
        "libertex.com": [
            [".", *H[1:]],
            ["Еженедельный синк c командой клиента", D, S28, "В работе", "1"],
            ["Еженедельный синк c командой клиента", D, S05, "", "1"],
            ["Внутренний созвон по Libertex", D, S28, "В работе", "0.5"],
            ["Операционка по проекту", D, S28, "В работе", "0.5"],
            ["Коммуникация с клиентом", D, S28, "В работе", "1.5"],
            ["Обновление статьи https://libertex.com/de/blog/xiaomi-aktie-prognose", D, S28, "", "0.4"],
        ],
        "ads.yandex.com": [
            H,
            ["SEO-аудит страницы Direct под запросы пользователей и LLM", D, S28, "В работе", "2"],
            ["Ссылочная стратегия под GEO", D, S28, "Выполнено", "1"],
            ["Коммуникация с клиентом по SEO-вопросам", D, S28, "В работе", "2"],
            ["Еженедельный созвон с клиентом", D, S28, "В работе", "1"],
            ["ТЗ на оптимизацию контента для ранжирования в ИИ", D, S28, "В работе", "1"],
            ["ТЗ на оптимизацию контента для ранжирования в ИИ", D, S28, "В работе", "1"],
        ],
        "hero-sms.com": [
            H,
            ["hero-sms — внутренний синк", Y, S28, "", "0.5", "0.9"],        # hand value, no match
            ["hero-sms — внутренний синк", A, S28, "", "0.5"],
            ["Еженедельный чекап", A, S19, "", "0.3", "0"],                  # future sprint
            ["Коммуникация с клиентом", Y, S28, "", "2"],
            ["Отчёт по ОП", Y, S28, "", "3"],                                 # near-match
            ["Сателлиты"],                                                    # section row
        ],
        "appliancepro.care": [
            H,
            ["Создание проекта в сервисе BrightLocal", Y, "28.09 - 04.10", "В работе", "2"],
            ["Отчет за 1/2 ОП", Y, "28.09 - 04.10", "В работе", "1", "1.3"],
            ["Консультации по контенту карточки Yelp", Y, "21.09 - 27.09", "Блокер", "2", "0.6"],
            ["Линкбилдинг для cupertino-appliance-repair.com (заказ прогона)", Y, "28.09 - 04.10", "В работе", "0.5"],
            ["Создание сателлита для дополнительной локации redwood city", Y, "28.09 - 04.10", "В работе", "4"],
            ["Закрытие от индексации дублирующихся страниц сайта без трафика", Y, "10.08 - 16.08", "Выполнено", "0.5"],
        ],
        "planner5d.com": [
            H,
            ["Entity Map and Consolidation Architecture for the AI Cluster", Y, "14.09 -20.09", "Выполнено", "2.5", "2.5"],
            ["Extractability Audit and Reverse Relevance Engineering (AI Visibility)", A, "28.09 - 04.10", "В работе", "1.5"],
            ["Technical Specifications for the Pages of the AI Cluster", Y, "21.09 - 27.09", "Выполнено", "4", "3.8"],
            ["Technical Specifications for the Pages of the AI Cluster", Y, "28.09 - 04.10", "В работе", "4.5"],
        ],
        "plg.bet": [H, ["#REF!", "#REF!", "#REF!", "#REF!", "#REF!", "#REF!"]],
        "priceva.com": [H, ["Подготовка 10 ТЗ", "Валера", "8", "Готово", "8", "8"]],
    }


BOARDS = {
    3683118167: {"cols": {"hours": "_____5", "tags": "____"}, "groups": {
        "Спринт 28.09.2026 - 04.10.2026": [
            ("13147072297", "Еженедельный синк c командой клиента", "", "колл, регулярная, libertex.org, libertex.com"),
            ("13147072296", "Внутренний созвон по Libertex", "", "планерка, регулярная, libertex.org, libertex.com"),
            ("13147072294", "Операционка по проекту", "0.5", "регулярная, libertex.com"),
            ("13147072293", "Коммуникация с клиентом", "1", "регулярная, libertex.org, libertex.com"),
            ("13147072295", "Коммуникация с клиентом по SEO-вопросам", "0.2", "регулярная, ads.yandex.com"),
            ("13146971086", "Еженедельный синк c командой клиента", "1", "колл, регулярная, ads.yandex.com"),
            ("13146971088", "Проверка почему отключились сателлиты", "1", "satellite, libertex.com"),
            ("13146971092", "Ссылочная стратегия под GEO", "", "регулярная, ads.yandex.com"),
            ("13147074588", "SEO-аудит страницы Direct под запросы пользователей и LLM", "", "регулярная, ads.yandex.com"),
            ("13149000841", "ТЗ на оптимизацию контента для ранжирования в ИИ", "", "регулярная, ads.yandex.com"),
            ("13149000842", "ТЗ на оптимизацию контента для ранжирования в ИИ", "", "регулярная, ads.yandex.com"),
        ],
        "Шаблон Спринта": [("1", "template", "5", "libertex.com")],
    }},
    7120872180: {"cols": {"hours": "numeric__1", "tags": "tag__1"}, "groups": {
        "Спринт 28.09.2026-04.09.2026": [
            ("13168783969", "hero-sms — внутренний синк", "0.5", "hero-sms.com"),
            ("13148013357", "Extractability Audit and Reverse Relevance Engineering (AI Visibility) (copy)", "", "planner5d.com"),
        ],
    }},
    18393117669: {"cols": {"hours": "numeric_mkyy6m6c", "tags": "____"}, "groups": {
        "Спринт 28.09.2026 - 05.10.2026": [
            ("13091695605", "Коммуникация с клиентом", "0.2", "weekly, hero-sms.com"),
            ("13147889562", "Отчёт за ОП", "3.2", "hero-sms.com"),
            ("13147830194", "Создание проекта в сервисе BrightLocal", "0", "appliancepro.care"),
            ("13147325647", "Отчет за 1/2 ОП", "1.3", "appliancepro.care"),
            ("13147869188", "Линкбилдинг для cupertino-appliance-repair.com (заказ прогона)", "0.2", "appliancepro.care"),
            ("13147840645", "Сателлит по Redwood city", "3.3", "appliancepro.care"),
            ("13132777776", "Technical Specifications for the Pages of the AI Cluster x3", "", "planner5d.com"),
        ],
        "Спринт 21.09.2026 - 28.09.2026": [
            ("13091762966", "Консультации по контенту карточки Yelp", "0.6", "appliancepro.care"),
            ("13079469284", "Technical Specifications for the Pages of the AI Cluster x2", "3.8", "planner5d.com"),
            ("13037571533", "Проверить работу .de сателлитов Дениса", "0.4", "libertex"),
        ],
        "Спринт 14.09.2026 - 21.09.2026": [
            ("13038176679", "Entity Map and Consolidation Architecture for the AI Cluster", "2.5", "planner5d.com"),
        ],
    }},
}


class FakeSheets:
    def __init__(self, data):
        self.data = data
        self.writes = []

    def tab_titles(self):
        return list(self.data)

    def read(self, ranges):
        out = []
        for r in ranges:
            tab = r.rsplit("!", 1)[0].strip("'").replace("''", "'")
            out.append([list(x) for x in self.data[tab]])
        return out

    def write(self, data):
        self.writes += data
        for d in data:
            tab, cell = d["range"].rsplit("!", 1)
            tab = tab.strip("'")
            col = ord(cell[0]) - 65
            row = int(cell[1:])
            rows = self.data[tab]
            while len(rows) < row:
                rows.append([])
            r = rows[row - 1]
            while len(r) <= col:
                r.append("")
            r[col] = str(d["values"][0][0])


class FakeReader:
    def board_meta(self, bid):
        b = BOARDS[bid]
        cols = [{"id": b["cols"]["hours"], "title": "Часы факт", "type": "numbers"},
                {"id": b["cols"]["tags"], "title": "Теги", "type": "tags"},
                {"id": "date4", "title": "Дедлайн", "type": "date"}]
        groups = [{"id": f"g{i}", "title": t, "position": str(i)} for i, t in enumerate(b["groups"])]
        return {"columns": cols, "groups": groups}

    def group_items(self, bid, gid, cols):
        title = list(BOARDS[bid]["groups"])[int(gid[1:])]
        b = BOARDS[bid]
        return [{"id": i, "name": n, "column_values": [
            {"id": b["cols"]["hours"], "text": h}, {"id": b["cols"]["tags"], "text": t},
            {"id": "date4", "text": "2026-10-01"}]} for i, n, h, t in BOARDS[bid]["groups"][title]]


def cell(sheets, tab, a1):
    col, row = ord(a1[0]) - 65, int(a1[1:])
    r = sheets.data[tab][row - 1]
    return r[col] if len(r) > col else ""


def test_parsers():
    assert sync.parse_group_start("Спринт 28.09.2026-04.09.2026") == dt.date(2026, 9, 28)
    assert sync.parse_group_start("Спринт 15.06.26-21.06.26") == dt.date(2026, 6, 15)
    assert sync.parse_group_start("Duplicate of Шаблон Спринта") is None
    anchors = [dt.date(2026, 9, 28)]
    assert sync.parse_sheet_sprint("14.09 -20.09", anchors) == dt.date(2026, 9, 14)
    assert sync.parse_sheet_sprint("19.10.2026 -25.10.2026", anchors) == dt.date(2026, 10, 19)
    assert sync.parse_hours(".5") == 0.5 and sync.parse_hours("0") == 0.0 and sync.parse_hours("") is None


def test_normalization():
    n = sync.normalize_name
    assert n("hero-sms — внутренний синк", "hero-sms.com") == n("Внутренний синк - hero-sms", "hero-sms.com")
    assert n("Technical Specifications for the Pages of the AI Cluster x3", "planner5d.com") == \
        n("Technical Specifications for the Pages of the AI Cluster", "planner5d.com")
    assert n("Обновление предикшинов - 6 шт", "x") == "обновление предикшинов"
    assert n("Extractability Audit (copy)", "x") == "extractability audit"
    assert sync.match_key("Обновление статьи UPD1: https://libertex.org/es/blog/cafe-prediccion", "libertex.org") == \
        sync.match_key("Обновление https://libertex.org/es/blog/cafe-prediccion/", "libertex.org")


def test_monday_is_read_only():
    r = sync.MondayReader.__new__(sync.MondayReader)
    try:
        r.query("mutation { archive_item(item_id: 1) { id } }")
    except RuntimeError as e:
        assert "mutation" in str(e)
    else:
        raise AssertionError("mutation was not blocked")


def test_full_run_matches_manual_result():
    sh = FakeSheets(sheet_data())
    rep = sync.run(CFG, sh, FakeReader(), apply=True)
    assert not rep.stopped, rep.stopped
    # hours written
    assert cell(sh, "libertex.com", "F5") == "0.5" and cell(sh, "libertex.com", "G5") == "13147072294"
    assert cell(sh, "libertex.com", "F6") == "1"
    assert cell(sh, "ads.yandex.com", "F4") == "0.2"
    assert cell(sh, "hero-sms.com", "F3") == "0.5"
    assert cell(sh, "hero-sms.com", "F5") == "0.2"
    assert cell(sh, "appliancepro.care", "F2") == "0"
    assert cell(sh, "appliancepro.care", "F5") == "0.2"
    # IDs without hours
    assert cell(sh, "libertex.com", "G2") == "13147072297" and cell(sh, "libertex.com", "F2") == ""
    assert cell(sh, "ads.yandex.com", "G6") == "13149000841" and cell(sh, "ads.yandex.com", "G7") == "13149000842"
    assert cell(sh, "planner5d.com", "G3") == "13148013357"
    assert cell(sh, "planner5d.com", "G5") == "13132777776" and cell(sh, "planner5d.com", "G4") == "13079469284"
    assert cell(sh, "planner5d.com", "G1") == "monday_item_id"
    # never touched
    assert cell(sh, "hero-sms.com", "F2") == "0.9"          # hand-entered, no match
    assert cell(sh, "hero-sms.com", "F4") == "0"            # future sprint
    assert cell(sh, "appliancepro.care", "F6") == ""        # near-match only
    assert cell(sh, "appliancepro.care", "G7") == ""        # older than window
    for w in sh.writes:                                      # only F and G
        assert w["range"].split("!")[1][0] in "FG", w
    reasons = {(t, n): why for t, n, _, _, why in rep.unmatched_rows}
    assert reasons[("hero-sms.com", 6)].startswith("near-match: 'Отчёт за ОП'")
    assert reasons[("appliancepro.care", 6)].startswith("near-match")
    skipped = dict(rep.skipped_tabs)
    assert "plg.bet" in skipped and "priceva.com" in skipped
    assert any(it.id == "13146971088" for it in rep.unmatched_items)
    assert any(it.id == "13037571533" for it in rep.unmatched_items)   # report-only 'libertex' tag

    # second night: nothing changes, rows are matched by ID
    n_writes = len(sh.writes)
    rep2 = sync.run(CFG, sh, FakeReader(), apply=True)
    assert len(sh.writes) == n_writes and not rep2.f_changes and rep2.g_changes == 0


def test_monthly_reset_detection():
    data = sheet_data()
    # someone rebuilt the list but left old IDs in G: most IDs now point to the wrong rows
    data["ads.yandex.com"][1] += ["", "13147072294"]   # item of libertex.com -> stale
    data["ads.yandex.com"][2] += ["", "13091695605"]   # item on another board -> stale
    data["ads.yandex.com"][3] += ["5", "13147072295"]  # still valid
    sh = FakeSheets(data)
    rep = sync.run(CFG, sh, FakeReader(), apply=True)
    assert rep.reset_tabs == ["ads.yandex.com"] and rep.stopped and not sh.writes


def test_single_stale_id_is_cleared_and_rematched():
    data = sheet_data()
    for r in data["planner5d.com"][1:]:
        while len(r) < 6:
            r.append("")
    data["planner5d.com"][1].append("13038176679")   # valid
    data["planner5d.com"][2].append("13038176679")   # stale: wrong sprint and board
    data["planner5d.com"][3].append("13079469284")   # valid
    sh = FakeSheets(data)
    rep = sync.run(CFG, sh, FakeReader(), apply=True)
    assert not rep.stopped
    assert [s[1] for s in rep.stale] == [3]
    assert cell(sh, "planner5d.com", "G3") == "13148013357"


def test_safety_stop_on_too_many_changes():
    cfg = dict(CFG, max_f_changes=2)
    sh = FakeSheets(sheet_data())
    rep = sync.run(cfg, sh, FakeReader(), apply=True)
    assert rep.stopped and not sh.writes


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
