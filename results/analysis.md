# Results and analysis (formal runs, 2026-10-20)

Model `deepseek-flash` (DeepSeek-V4.1-Flash), thinking disabled, temperature 0. Same system prompt,
tool specs, column notes and budgets (T <= 8 tool calls, R <= 2 repairs) for all modes.
All numbers below are recomputed from `formal.jsonl` and `faults.jsonl` by `python -m evaluation.figures`.

## Headline numbers

| | baseline | raw_retry | proposed |
| --- | --- | --- | --- |
| Natural task success (120 runs each) | 100.0% | 100.0% | 100.0% |
| Recovery on injected faults (30 runs each) | 10.0% | 93.3% | 100.0% |
| Fault runs: mean tool calls | 1.20 | 2.87 | 2.10 |
| Fault runs: mean model requests | 1.30 | 3.87 | 3.10 |
| Fault runs: mean tokens | 3,817 | 13,174 | 9,814 |
| Fault runs: median latency (s) | 2.75 | 10.82 | 8.14 |
| Natural runs: mean tokens | 7,136 | 7,169 | 7,132 |
| Natural runs: median latency (s) | 5.50 | 5.52 | 5.56 |

Paired exact McNemar tests on the fault runs (paired by fault and repeat):
baseline vs raw_retry 0 vs 25 discordant runs, p = 6.0e-8; baseline vs proposed 0 vs 27, p = 1.5e-8;
raw_retry vs proposed 0 vs 2, p = 0.5 (not significant).

Total usage of all 450 runs: 3,243,810 prompt tokens and 132,834 completion tokens; at the
2026-10-20 list price ($0.15 / $0.60 per 1M input / output tokens off-peak, double at peak) this is
roughly USD 0.57-1.13.

Figures: `figures/fig1_success_vs_recovery.png`, `figures/fig2_fault_cost.png`, `figures/fig3_per_fault.png`.

## Findings

1. **Natural tasks are at ceiling.** With exact column names, a data summary and column notes in the
   prompt, the model made only one tool error in 360 runs (B19, raw_retry: a percent chart without
   `unit="fraction"`, repaired in one round). Validation added no measurable cost when nothing went
   wrong (tokens and latency are equal across modes).
2. **Being allowed to retry explains most of the recovery.** After an injected error, baseline stops and
   recovers only 3/30 runs; returning the raw error with two repair rounds raises recovery to 28/30.
3. **Structured, dataset-aware feedback makes recovery reliable and cheaper.** Proposed recovered 30/30
   runs, always in exactly one repair round, with 27% fewer tool calls, 20% fewer model requests,
   26% fewer tokens and 25% lower median latency than raw_retry. The success difference over raw_retry
   (2 runs) is not statistically significant; the efficiency difference is consistent across faults.
4. **Where raw errors are not enough (F08: `sum` of the text date column `dteday`).** The raw message
   "sum and mean require a known numeric column" does not say which columns are numeric. In 2 of 3
   runs the model then tried to filter on `dteday < "2012-01-01"` (a second error), used both repairs,
   and finally answered from a table grouped by year instead of the requested filtered total. Its
   number (1,243,103) was right, but the cited table does not match the task, so the frozen rule scores
   it as a failure. With proposed, the feedback "`sum` needs a numeric column, but 'dteday' is text"
   plus the list of numeric columns led straight to `sum(cnt)` with the `yr = 0` filter.
5. **A silent fault (F04: `Sex = "Female"`).** This filter is legal and returns 0 rows with an
   `EMPTY_RESULT` warning instead of an error, so baseline does not stop. In all three baseline runs the
   model noticed the empty result and re-queried with `"female"`: these are baseline's only recoveries.
   Proposed rejects the unknown category before execution and suggests `female`.

## Limitations

- One model, two datasets and 10 hand-designed faults; the natural set did not produce enough organic
  errors to compare modes on natural tasks.
- Faults are injected into the first call of one tool; real errors may be harder (wrong semantics with
  valid arguments), which the validator cannot detect.
- Scoring is strict by design (cited table must match the requested grouping). Under a lenient rule that
  accepts any table containing the correct value, raw_retry would also reach 30/30 on faults.
- The comparison-answer check only verifies that the winning group is named before a losing group.
