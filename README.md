# monday-hours-sync

Copies actual hours ("Часы факт") from specialists' monday.com boards into the Google Sheet
"Планирование задач на проектах SEO Global" every night. monday.com is only read, never changed.
In the sheet, only column F ("Часы факт") and column G ("monday_item_id") are written.

How matching works: [docs/nightly-sync-algorithm.md](docs/nightly-sync-algorithm.md).

## Files

| File | What it is |
|---|---|
| `sync.py` | The sync script |
| `config.yaml` | Specialists and their boards, tag aliases, ignored tags, safety limits — the only file to edit |
| `CLAUDE.md` | Instructions for the nightly Claude Code run |
| `tests/test_sync.py` | Offline tests built from real data of 30.09.2026 |

## One-time setup

1. **monday.com token.** monday.com → avatar → Developers → My access tokens → copy.
   The script refuses to send mutations, but a token can do whatever its user can, so a
   token of a user with viewer rights on the 8 boards is safest.
2. **Google service account.**
   1. console.cloud.google.com → create a project → APIs & Services → enable **Google Sheets API**.
   2. IAM & Admin → Service accounts → Create → Keys → Add key → JSON. Download the file.
   3. Open the sheet → Share → add the service account's email (…@….iam.gserviceaccount.com) as **Editor**.
3. **Claude Code environment** (claude.ai/code → environment settings):
   - secrets: `MONDAY_TOKEN` = the token, `GOOGLE_SA_JSON` = the whole JSON file content;
   - network access: allow `api.monday.com`, `sheets.googleapis.com`, `oauth2.googleapis.com`.
4. **Scheduled task** in Claude Code on this repo, every day at 02:00 Moscow time
   (`CRON_TZ=Europe/Moscow 0 2 * * *`), prompt: *"Run the nightly sync as described in CLAUDE.md."*

## Running on GitHub Actions (no Claude needed)

`.github/workflows/sync.yml` runs the tests and then the sync every night at 02:00 Moscow time
(`--apply`), and on demand from the Actions tab (choose `dry-run` or `apply`).

1. Repository → Settings → Secrets and variables → Actions → New repository secret:
   `MONDAY_TOKEN` = the monday.com token, `GOOGLE_SA_JSON` = the whole JSON key file content.
2. Merge the workflow into the default branch: GitHub runs scheduled workflows only from there.
3. Each run shows the report and the log in its summary page and keeps them as a downloadable
   artifact for 90 days. A failed run (tests fail, safety stop, error) is marked red and GitHub
   emails the repository owner.

Unlike the Claude run, the workflow doesn't check for "more than 3×" or "number → empty" overwrites
(see CLAUDE.md, step 4); the script's own safety stop and reset detection still apply.

## Running by hand

```bash
pip install -r requirements.txt
export MONDAY_TOKEN=...  GOOGLE_SA_JSON=/path/to/key.json
python sync.py --dry-run                       # plan + report, writes nothing
python sync.py --apply --report reports/today.md
python sync.py --dry-run --tabs "hero-sms.com,planner5d.com"   # only some tabs
python -m pytest -q tests
```

Every run (dry or apply) also writes `logs/log-YYYY-MM-DD_HH-MM-SS.log` with the cells actually
written (`tab!F12: old -> new`) and the errors: safety stop, unreadable boards, skipped tabs, cells changed
during the run, and the traceback if the script crashed. `--log-dir` changes the folder.

Exit code 1 means a safety stop (nothing was written): reset detection fired on a tab, or more than
`max_f_changes` cells would change.

## Every month, when the task list is rebuilt

Clear **columns F and G together** on every rebuilt tab. If someone forgets, the sync notices that
most IDs in G no longer fit their rows, writes nothing to that tab and says so in the report.
