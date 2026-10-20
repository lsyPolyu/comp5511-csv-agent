# COMP5511 Local CSV Analysis

The Streamlit page uploads one CSV, inspects its real data, and performs local
filtering, grouping and statistics. It displays a five-row preview, column types,
missing-value summaries and a separate statistics result table, then generates
bar or line charts from that real result with a PNG download. No API key or
model is used. P01, P02 and P03 are complete.

## Run on Windows

From PowerShell:

```powershell
Set-Location -LiteralPath 'F:\JavaAiNew\agent_project\COMP5511'
.\.venv\Scripts\python.exe -m pip check
netstat -ano -p tcp | Select-String -Pattern ':8501\s.*LISTENING'
# Start only if the port is free; otherwise reuse the existing project page:
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Open <http://127.0.0.1:8501>. If the port is occupied, inspect the listener or
choose another port; do not stop an unidentified process. Stop a server started
in your terminal with Ctrl+C.

After changing imported UI module interfaces, restart the identified project
server using the same environment and command, then verify an actual CSV upload.
A browser refresh and an HTTP health check do not prove that a long-running
Python process has reloaded its imported modules. A server restart ends the
in-memory sessions, so upload the CSV again after refreshing the original URL.

Use the existing project `.venv` (Python 3.12.4). If dependencies are missing,
install the exact locked versions into that environment:

```powershell
.\.venv\Scripts\python.exe -m pip --isolated install --no-cache-dir --progress-bar off --only-binary=:all: --index-url https://pypi.org/simple --disable-pip-version-check -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
```

For a fresh checkout without `.venv`, create it first using Python 3.12.4. On the
development machine the explicit bootstrap interpreter is:

```powershell
& 'F:\JavaAiNew\software\anaconda3\python.exe' -m venv .venv
```

`requirements.txt` declares runtime dependencies, `requirements-dev.txt` adds
pytest, and `requirements-lock.txt` pins the complete tested Windows environment.
Do not recreate an intact environment or upgrade packages during recovery.

## Accepted CSV input

- One comma-separated `.csv` file with a header, encoded as UTF-8 or UTF-8-BOM.
- At most 20 MiB and 100,000 data rows. These are enforced input limits, not
  performance guarantees.
- Nonempty, unique column names. Original names, case and surrounding spaces
  are preserved.
- Only empty fields count as missing; `NA`, `N/A` and `null` remain literal text.
- A column is numeric only when all nonmissing values parse as finite numbers.
  Mixed columns remain text; an entirely missing column has type `unknown`.

Empty files, header-only files, malformed quoting, inconsistent row widths and
invalid headers produce English errors. Replacing or removing a file clears the
previous dataset, including when the replacement is invalid. Original uploaded
bytes and parsed source records remain immutable; uploads are held in the
current session rather than saved to disk.

## Interface language

Use **English / 中文** at the top of the page. English is the default for each
new session and for course demonstrations. Chinese is available for local
operation and acceptance checks; it does not enable Chinese agent questions or
change English evaluation tasks, experiment settings or course deliverables.

Application labels, help, summary headers, status messages and error explanations
follow the selected language. Technical options show their Chinese names with
the original tokens, such as `平均值（mean）`. CSV column names, category values,
data, aliases, IDs, tool schema fields/enums and error codes are preserved.
Chinese errors include a deterministic explanation and the original English
detail; no translation service or model is called.

Switching language preserves selected controls and the uploaded dataset,
statistics and existing chart, including all IDs and PNG bytes. It does not
reload, calculate or redraw. Control edits synchronize to the session, while
**Run statistics** and **Generate chart** remain the only execution triggers.
Unedited chart defaults follow the language; user-entered title/axis text is
retained. Percent defaults include `(%)`. Click Generate chart explicitly to
create a new chart with the current text.

The native Streamlit uploader's internal **Browse files** and drag/drop prompts
remain English: the locked [file uploader API](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)
does not expose translations for those strings. The application supplies a
Chinese label and help explaining how to use it. Browser/OS dialogs also follow
their own language. No framework files, CSS text replacements or dependencies
were changed to simulate translation.

Chinese chart rendering uses the installed **Microsoft YaHei** font at
`C:\Windows\Fonts\msyh.ttc`, checked against the actual requested glyphs.
Matplotlib uses `font.family = ["DejaVu Sans", "Microsoft YaHei"]` only inside
the chart's `rc_context`, restoring previous settings afterwards. On another
machine it checks SimHei, Noto Sans CJK SC, Noto Sans SC and WenQuanYi Zen Hei
as alternatives. If no installed font covers the labels, generation returns
`PLOT_RENDER_ERROR` instead of silently delivering missing glyphs. Fonts are not
bundled or installed automatically. Chinese PNG examples and font evidence are
in `outputs/dev/p03/i18n/`.

## Run local statistics

1. Upload `data/dev/eight_rows.csv`.
2. Set **Number of metrics** to 4 first. Keep filters and sort keys at 0 and
   **Group by** empty. Configure:

   | Operation | Column | Alias |
   | --- | --- | --- |
   | row_count | No column (row_count) | rows |
   | count | Age | valid_age |
   | sum | Age | total_age |
   | mean | Age | mean_age |

3. Click **Run statistics**. The single result row is `8`, `6`, `160`, and
   `80 / 3` (approximately `26.6666667`). Display rounding does not change the
   stored result.
4. For a grouped example, set the number of metrics to 1 first, select **Sex**
   in **Group by**, and configure `mean`, `Survived`, alias `rate`. Submit again:
   female has `0.75`, male has `0.25`.
5. To filter that example, set the number of filters to 1 first and configure
   column `Age`, operator `ge`, value `30`. Submit: 3 rows remain, with female
   `0.5` and male `0`. For sorting, add a sort key naming the exact grouping
   column or metric alias (for example `rate`) and choose `asc` or `desc`.

Set row counts before editing the form. The form offers up to 10 filters, metrics
and sort keys each. All filters use AND. Supported operators are
`eq`, `ne`, `gt`, `ge`, `lt`, `le`, `in`; for `in`, enter one value per line.
Numeric columns require finite numeric values; text values remain literal.
`row_count` uses no target column, while the other operations require one.
Aliases must be nonblank, unique, and different from grouping column names.

Only **Run statistics** starts a new run. Changing controls or an ordinary page
rerun leaves the last submitted result visible; its source is shown by Dataset,
Run and Result IDs and the **Calculation details** section. A new submission
invalidates old run references, including when the new calculation fails.
Replacing/removing an upload invalidates all its results, even if parsing the
replacement fails. An already loaded P01 upload is preserved when the upgraded
page initializes its new session state.

Missing values never match filters, including `ne`. A legal zero-row filter is a
successful result with `EMPTY_RESULT`: without grouping it returns one row of
zero counts and null sums/means; with grouping it returns an empty table with
field definitions. A known numeric column with no values in a result group has
null sum/mean and `NO_VALID_VALUES`; an entirely missing `unknown` column rejects
sum/mean. Missing grouping keys are retained and use a display label that cannot
collide with real categories; the stored key remains JSON null. Sorting is
stable, defaults to ascending grouping keys, and puts null last in both directions.

Successful results include source session/dataset/run IDs, a result ID, selected
row count, field definitions, computed result rows and normalized operations.
Each session owns its result registry; foreign, stale and unknown references
return `INVALID_RESULT_REFERENCE`. Source uploads are not changed by analysis.

## Plot and download a statistics result

1. Run the grouped survival example above without filters: **Group by** = Sex,
   metric = mean(Survived), alias = rate. The result is female `0.75`, male `0.25`.
2. In **Chart from statistics**, keep **Chart type** = bar, **X field** = Sex,
   **Y field** = rate. Set **Chart title** = `Survival by sex`, **X-axis label** =
   `Sex`, **Y-axis label** = `Survival rate (%)`, **Y format** = percent,
   **Decimal places** = 2, and **Unit** = fraction. Keep **X kind** = default
   and **Date format** empty. Click **Generate chart**.
3. Check **Underlying plot data**: y remains `0.75` / `0.25`, while display_y
   shows `75.00%` / `25.00%`. **Chart source and format** records the source
   result/session/dataset/run, fields, operations, labels and explicit formats.
   Click **Download chart (PNG)** to save the displayed chart.
4. To display fractions directly, choose **Y format** = number and use
   `Survival rate (fraction)` as the Y-axis label. Keep **Unit** = fraction;
   two decimal places display `0.75` / `0.25`.

Charts accept existing result fields, never entered numeric arrays. Bar charts
retain result order, including separate bars for repeated x labels. Line charts
sort x stably and require finite numeric values or explicit ISO dates; they do
not aggregate repeated x values. For a numeric example, upload
`outputs/dev/p03/recovery-examples/numeric_line.csv`, group by Year, and use
sum(Revenue) with alias Revenue. Generate a line chart with X field Year,
Y field Revenue, X-axis label `Year`, Y-axis label `Revenue (USD)` and Unit USD.
The underlying points are `(2020, 10)`, `(2021, 20)`, `(2022, 30)`.

For dates, upload `outputs/dev/p03/recovery-examples/date_line.csv`, group by
Date and use the same Revenue metric. Select line, X field Date, **X kind** =
date, **Date format** = `%Y-%m-%d`, and X-axis label `Date`. Dates sort ascending
and keep their actual calendar spacing. Other date formats, impossible dates,
missing line x values and nonnumeric y fields are rejected. Partial missing y
values remain gaps with a warning; empty or entirely missing y data produces an
error. Only empty category values receive a distinct missing label.

Title and axis labels must be nonblank printable text; Chinese is supported for
local acceptance. Unit remains nonblank English text. Percent requires
unit=fraction and a Y-axis label containing `(%)` or `(percent)`; decimal places
must be an integer from 0 to 6. Display rounding is shared by axis ticks and
plot metadata and never changes the source result. An invalid chart request
shows an error and retains the clearly labelled last successful chart.

Generating/downloading a chart and ordinary page reruns do not rerun statistics.
A new statistics submission, even a failed one, clears the old chart and its
download. Replacing/removing the CSV also clears them, including failed loads.
Stale and cross-session result/chart references are rejected. Figures are
rendered in memory and cleared; each session keeps only its current PNG.

## Verify P01, P02 and P03

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests exercise CSV contracts, independent hand-calculated statistics, real chart
data, strict dates, display formats, result ownership, and the actual
upload/statistics/chart/download forms with Streamlit AppTest. They cover normal,
invalid, empty and missing-value cases; sorting and date spacing; tiny percentage
rounding boundaries; replacement, clear/reupload, separate sessions, reruns and
session upgrades. The latest P03 live-entry fix passed **267 tests**, including
the existing P01–P03 regressions. Both English and Chinese workflows, pending
control preservation, unchanged references/artifacts, deterministic errors and
Chinese fonts are covered. Representative PNGs were generated through AppTest
and visually inspected at original resolution, with no missing-glyph warnings.
AppTest does not verify the browser's operating-system file picker, rendered
page layout, actual browser download-to-disk or browser-specific event behavior.
Current evidence is in `outputs/dev/p03/i18n/`; earlier P03 evidence remains in
`outputs/dev/p03/recovery-*`, with status and
limitations in `docs/HANDOFF.md`.

The live-entry fix also verifies the actual restarted service through its local
HTTP/WebSocket protocol in both languages, including upload, statistics, chart
generation, PNG download, language switching and a new statistics run. Evidence
is in `outputs/dev/p03/live-entry-fix/`. This is backend verification, separate
from AppTest and browser rendering. The old service's stale single-argument
renderer failure and the successful restarted flow are recorded separately.

The existing P01 upload walkthrough remains available for a core-flow review:

1. Open the page and upload `data/dev/eight_rows.csv` using **Browse files**.
2. Check **Rows = 8**, **Columns = 3**, and a five-row preview with the original
   `Sex`, `Survived`, `Age` columns and a missing Age in the third preview row.
3. In **Column summary**, check Age is numeric, **Missing count = 2**, and
   **Missing ratio = 0.2500**. All application labels should be in English.
4. Replace the upload with a header-only CSV (`A,B` followed by a newline), then
   a malformed CSV (`A,B` followed by `1,2,3` on the next line). Local recovery
   examples are available in `outputs/dev/p01/manual/`. Expect
   `EMPTY_DATASET` and `CSV_PARSE_ERROR`, respectively, with no old preview or
   metrics remaining.
5. Remove the upload, then upload the sample again. Check the empty state clears
   the error and the successful upload receives a new **Dataset ID**.

An agent, model calls and formal experiments remain future work. The
eight-row file is a development fixture, not an evaluation dataset.

## Implementation notes

`contracts.py` validates strict arguments, `analysis.py` computes over immutable
typed Dataset records, `state.py` owns result/chart references, `statistics_ui.py`
renders the statistics controls, and `chart_ui.py` renders chart controls and PNG
download. `plotting.py` resolves registered results and renders with Matplotlib's
object-oriented Agg API, retaining original values and explicit display formats.
`i18n.py` owns static interface text, option display labels and error explanations;
the calculation modules do not depend on the selected UI language.
Pandas is used for disposable display frames;
filtering/grouping follow explicit Python rules so library NA defaults cannot
change the specified semantics. Official API references used for this stage:
[session state](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state),
and [Pydantic strict validation](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/).
