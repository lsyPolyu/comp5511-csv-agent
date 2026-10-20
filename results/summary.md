# Experiment summary

## Natural tasks

| Mode | Runs | Success rate | 95% CI | Median latency (s) | p95 latency (s) | Mean model requests | Mean tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 120 | 100.0% | 100.0%-100.0% | 5.496 | 8.93 | 2.30 | 7136 |
| raw_retry | 120 | 100.0% | 100.0%-100.0% | 5.5169999999999995 | 9.13 | 2.31 | 7169 |
| proposed | 120 | 100.0% | 100.0%-100.0% | 5.555 | 9.03 | 2.30 | 7132 |

Failure reasons: {"baseline": {}, "raw_retry": {}, "proposed": {}}

- McNemar baseline_vs_raw_retry: {'only_baseline': 0, 'only_raw_retry': 0, 'p_value': 1.0}
- McNemar baseline_vs_proposed: {'only_baseline': 0, 'only_proposed': 0, 'p_value': 1.0}

## Injected faults

| Mode | Runs | Triggered | Recovered | Recovery rate |
| --- | --- | --- | --- | --- |
| baseline | 30 | 30 | 3 | 10.0% |
| raw_retry | 30 | 30 | 28 | 93.3% |
| proposed | 30 | 30 | 30 | 100.0% |
