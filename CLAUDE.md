# Nightly sync agent: monday.com "Часы факт" → Google Sheet

You run the nightly sync of actual hours from specialists' monday.com boards into the Google Sheet
"Планирование задач на проектах SEO Global" (ID `17Ucxb0Nze7ZJCTH8AD-ZTn2Dl4nbYpWw0O2xwtLIelc`),
column F ("Часы факт") and column G ("monday_item_id") of each project tab.

The full algorithm is in `docs/nightly-sync-algorithm.md`. `sync.py` implements it; `config.yaml`
holds the settings.

## Hard rules (never break these)

1. monday.com is **read-only**. Never send mutations, never change, move, archive or delete items,
   groups, columns or boards — not through `sync.py`, not through any monday.com connector tool.
2. On monday.com only the 8 most recent sprint groups of each board are read. `sync.py` does this;
   don't read other groups yourself.
3. In the sheet, only columns F and G are written, and only by `sync.py`. Never edit columns A–E,
   never add, delete, reorder or rename rows or tabs, never edit cells by hand through other tools.
4. Never edit `config.yaml` or `sync.py` during a nightly run. Suggest changes in the report instead.
5. If anything is ambiguous, don't guess: leave the cell and list the case in the report.

## Nightly procedure

1. `pip install -q -r requirements.txt`
2. `python -m pytest -q tests` — if tests fail, stop and report; don't run the sync.
3. `python sync.py --dry-run --report reports/dry-run.md` and read the report.
4. Stop and report instead of applying when:
   - the report starts with **SAFETY STOP** (exit code 1), or
   - a change overwrites a non-empty F value with a very different number (more than 3× or
     from a number to empty) and the row wasn't in "Stale IDs cleared", or
   - reading a board or the sheet failed.
5. Otherwise: `python sync.py --apply --report reports/apply.md`.
6. Each run writes `logs/log-<date_time>.log` (cells written + errors). Mention its file name in the report.
7. Send the apply report as your final message, adding at the top a 2–3 line summary:
   cells written, anything that needs a person (reset detection, unreadable boards,
   specialists without a board, new tags to alias).

## Secrets and network

- `MONDAY_TOKEN` — monday.com API token. Use a token of a user with viewer access if possible.
- `GOOGLE_SA_JSON` — Google service-account JSON (text or path). The sheet is shared with the
  service account's email as Editor.
- Allowed hosts: `api.monday.com`, `sheets.googleapis.com`, `oauth2.googleapis.com`, `pypi.org`,
  `files.pythonhosted.org`.
