# Nightly sync: monday.com "Часы факт" → Google Sheet

**Sheet:** Планирование задач на проектах SEO Global (`17Ucxb0Nze7ZJCTH8AD-ZTn2Dl4nbYpWw0O2xwtLIelc`)
**Schedule:** every day at 02:00 Moscow time (`CRON_TZ=Europe/Moscow 0 2 * * *`)
**Version:** 2, 30.09.2026. It adds column G (monday item ID) and fixes issues found during the first manual runs on 28.09.2026.

---

## 0. Hard rules

1. **monday.com is read-only.** Use GraphQL *queries* only, never mutations. Never change, move, archive or delete items, groups, columns or boards.
2. On each board, read only the **8 most recent sprint groups**. Never read the rest of the board.
3. In the sheet, write **only to column F ("Часы факт") and column G ("monday_item_id")**. Never edit columns A–E. Never add, delete, reorder or rename rows or tabs.
4. If a match is ambiguous, don't guess. Leave the cell as it is and list the case in the report.

---

## 1. Configuration (once, kept in `config.yaml`)

### 1.1 Specialist → board

The name in the sheet's "Спец" column is the key.

| Name in the sheet | Board ID |
|---|---|
| Панина Аня | 7120872180 |
| Сухенко Юрий | 18393117669 |
| Дубинко Денис | 3683118167 |
| Наташа Ходко | 18072517756 |
| Марина Ярославова | 18408563989 |
| Валера | 9276964627 |
| Вова | 9317710455 |
| Яна | 18420657783 |

Настя Хитрова and Владислав Щербаков have no board yet. Their rows are skipped and reported.

### 1.2 Monday tag → sheet tab

- By default the tag equals the tab name (libertex.com, libertex.org, hero-sms.com, appliancepro.care, planner5d.com …).
- Aliases: none needed today. The tab is named `ads.yandex.com`, the same as the tag.
  - `libertex` (a tag with no domain, seen on Юрий's board) → **report only**, because it's unclear whether it means .com or .org
- Ignored tags (not projects): регулярная, колл, планерка, satellite, weekly, обучение, операционка, СПК.

### 1.3 Tabs to skip

A tab is skipped and reported when:
- its column A contains `#REF!`, or
- its "Спринт" column holds numbers instead of a date range, or
- it can't be addressed by name through the API. `ads.yandex` returned "Unable to parse range" on 28.09. Tab names are read from the spreadsheet's metadata, never typed by hand.

### 1.4 Columns are found by title, not by ID

Each board has its own column IDs, so they are looked up by title on every run:

| Board | "Часы факт" | "Теги" |
|---|---|---|
| Денис Дубинко | `_____5` | `____` |
| Анна Панина | `numeric__1` | `tag__1` |
| Юрий Сухенко | `numeric_mkyy6m6c` | `____` |

In the sheet, columns are found by their header in row 1: "Спец", "Спринт" and "Часы факт". Column A is always the task name, even when its header is something odd like "." on the libertex.com tab.

---

## 2. Column G: "monday_item_id"

### 2.1 Purpose

Generic names like "Обновление статьи" can't be matched by name alone. Column G stores the ID of the monday item a row was matched to. Once a row has an ID, later runs match by ID and skip name matching entirely.

- **Format:** one item ID, or several IDs separated by commas when one row sums several items (for example `2134567890,2134567891`).
- **Header:** `monday_item_id` in G1. The column can be hidden.
- **Ownership:** a filled G cell means the value in F on the same row was **written by the sync**. An empty G means any value in F was entered **by hand**.

### 2.2 Monthly reset of the task list

Every month the task list in the tabs is rebuilt for the new reporting period. Old rows are replaced and new sprints are added. **Column G must be reset each time**, because old IDs would point new rows at old tasks.

This is the same failure that happened on 28.09. The libertex.com tab was restructured while column F kept values from the old layout, so for example "Внутренний созвон по Libertex, 12.10" showed 6 hours.

**Rule for whoever rebuilds the list each month:** clear **columns F and G together** on every rebuilt tab, or build the new list from a template where both are empty.

**The sync also protects itself, in case someone forgets:**

1. **Row check.** Before trusting an ID in G, confirm that:
   - the item is present in the 8 recent groups;
   - the item's group start equals the row's sprint start;
   - the item's tags include this tab.

   If any check fails, the ID is **stale**. The sync clears G and also clears F on that row, since that F value was written by the sync for a different task. The row then goes through normal name matching (step 4.4).
2. **Reset detection.** On a tab, if more than half of the filled G cells turn out stale in one run, treat it as a reset nobody cleared. Don't write anything to that tab. Report "task list changed, column G looks stale" and wait for a person to clear F and G. This prevents bulk overwrites caused by a half-edited sheet.
3. **Rows without IDs** (a fresh month) are matched by name, and their IDs are written to G. From the second night of the month on, those rows are matched by ID.

---

## 3. Reading

1. **Sheet.** Get the list of tabs and sheet IDs from the spreadsheet metadata. For each tab not on the skip list, read `A1:G`. Skip:
   - section rows, where only column A is filled (for example "Сателлиты");
   - `#REF!` rows.
2. **Sprint key.** Parse the **start date** of the "Спринт" value. Formats seen so far: `31.08 - 06.09`, `14.09 -20.09`, `28.09.2026 - 04.10.2026`, `19.10.2026 -25.10.2026`. When the year is missing, use the year of the nearest monday group. End dates are ignored: some tabs use Mon–Fri, others Mon–Sun.
3. **Monday.** For each specialist who has rows in these tabs:
   1. List the board's groups in board order.
   2. Keep only titles matching `^Спринт\s*(\d{2})\.(\d{2})\.(\d{2}|\d{4})\s*-\s*…`. Formats seen: `Спринт 28.09.2026 - 04.10.2026`, `Спринт 28.09.2026-04.09.2026`, `Спринт 15.06.26-21.06.26`.
   3. Take the first 8 that match. This skips "Шаблон Спринта", "Duplicate of Шаблон Спринта", "Регулярные задачи", "Часы на проекты" and similar.
   4. **Use only the start date of the group title.** End dates contain typos: Анна's "28.09.2026-04.09.2026" ends before it starts, and Юрий's sprints end on the next Monday.
   5. For each item, read its ID, name, "Часы факт", "Теги" and the group's start date.
4. **Hours values.** Parse `".5"` as 0.5. **`0` is a real value** and gets written. An empty value means no data.

---

## 4. Matching

### 4.1 Candidates

For every monday item, turn its project tags into tab names. An item tagged both libertex.com and libertex.org is a candidate for rows in **both** tabs. It's the same hours counted in two projects, so the report notes such items.

### 4.2 Match by ID (rows with G filled)

If the ID passes the row check in 2.2, the row matches that item (or the sum of those items). Go to step 5.

### 4.3 Sprints with no data

A sheet row gets **no match, silently and without a report entry**, when its sprint start is later than the newest monday group on that board, meaning a future sprint.

A row whose sprint falls inside the 8-group window, but whose board has **no group for that week**, is reported as "no sprint group". Examples: Юрий has no 07.09 group, Анна has no 21.09 group.

### 4.4 Match by name (rows with G empty)

A row matches an item when all four of these agree:
- the tab is among the item's project tags;
- the row's specialist owns the board;
- the sprint start dates are equal;
- the **normalized names** are equal.

Normalization, applied to both names:
1. Lowercase, trim, collapse spaces. Treat "—", "–" and "-" as the same character.
2. Remove the project name as a prefix or suffix: `hero-sms — внутренний синк` and `Внутренний синк - hero-sms` both become `внутренний синк`.
3. Remove `(copy)`.
4. Remove quantity suffixes `x2`, `х3`, `- 6 шт` at the end of the name.
5. Remove `UPD:2`, `UPD2:`, `UPD:`, `UPD1:` markers (anywhere in the name).

**URL rule (added in the script, 30.09.2026):** if a name contains a URL, the URL itself (without `https://`, `www.` and a trailing `/`) is the match key instead of the text. So "Обновление статьи UPD1: https://libertex.org/es/blog/cafe-prediccion" matches "Обновление https://libertex.org/es/blog/cafe-prediccion". An exact URL is stricter than a name, so this never adds a guess.

No fuzzy matching beyond this. Close but different names are **reported, not matched**. Examples from 28.09:
- "Создание сателлита для дополнительной локации redwood city" vs "Сателлит по Redwood city"
- "проверка выполненных работ разработчика" vs "Проверка внедрений разработчика"

### 4.5 Ambiguous cases

- **Several items → one row:** write the sum of their hours, and write all their IDs to G.
- **Several identical rows ↔ several items with the same name:** pair them in order of monday deadline, **only if the counts are equal**. Otherwise report. Example: 4 rows of "hero-sms — коммуникация с клиентом" vs 1 item.
- **Generic sheet names** ("Обновление статьи", "Крупный апдейт", "Новая статья CFD"): pair them in deadline order with that specialist's items in the same tab and sprint whose names start with the same first word ("Обновление …"), **only if the counts are equal**. Otherwise report. After one successful pairing the IDs sit in G, and later runs are stable.
- **Different granularity** (the sheet splits a task into 2 + 3 pages, monday has one task for 5 pages): report only.

---

## 5. Writing

For each matched row:

| Situation | F | G |
|---|---|---|
| Monday hours not empty, F empty or different | write monday hours | write item ID(s) |
| Monday hours not empty, equal to F | leave | write ID(s) if G is empty |
| Monday hours empty | leave empty | write ID(s), so the row is matched by ID next time |
| G was stale (step 2.2) | clear, then re-match | clear, then re-match |
| No match, G empty, F filled by hand | **never touch** | leave empty |

Monday is the source of truth. When a row is matched, its F follows monday even if someone typed a different number by hand. That change appears in the report as old → new.

Send all writes in **one batch per run** (`values.batchUpdate`, columns F and G only). Before writing, re-read `F:G` on the affected tabs. If a cell changed since step 3, skip it and report it.

**Safety stop:** if more than 50 F cells would change in one run, or reset detection fired on any tab, write nothing and send the report.

---

## 6. Report after each run

1. Date and time, number of F cells written, number of G cells written.
2. Table: tab | row | task | sprint | old F → new F.
3. Stale IDs cleared (step 2.2) and tabs where reset detection fired.
4. Monday items that have a project tag but no matching row.
5. Rows inside the 8-group window with no match, each with its reason: no sprint group, near-match (with both names), count mismatch, or different granularity.
6. Items counted in two tabs (for example libertex.com + libertex.org).
7. Skipped tabs and specialists without a board.
8. Suggested new aliases for `config.yaml`. The sync never edits the config itself.

---

## 7. What changed from version 1

- **Added:** column G "monday_item_id", its monthly reset rule, stale-ID detection and bulk-reset protection (section 2).
- **Changed:** the old rule "never clear a filled cell" was the reason wrong values stayed on libertex.com. It is now: never touch **hand-entered** F values (G empty). The sync may correct or clear F values it wrote itself (G filled).
- **Changed:** name normalization now removes the project name, `(copy)` and quantity suffixes. Without this, most rows on hero-sms.com and planner5d.com didn't match.
- **Changed:** monday group titles are parsed by start date only, because end dates contain typos. Title formats with and without spaces and with 2-digit years are supported.
- **Changed:** future sprints are skipped silently. Missing sprint weeks on a board are reported separately.
- **Changed:** column IDs are found by title on every board. Tab names come from the spreadsheet metadata.
- **Clarified:** `0` hours is a value and gets written; empty means no data.
- **Clarified:** items tagged with two projects are counted in both tabs and flagged in the report.
