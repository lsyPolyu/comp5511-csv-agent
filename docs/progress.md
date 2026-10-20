# Progress

| Date | Stage | Result |
| --- | --- | --- |
| 2026-10-20 | 0 Preflight | Git snapshot `76c74e8`. The linked computer's sandbox and the cloud sandbox have no internet (PyPI, DeepSeek, UCI unreachable); no `.env`, no `data/raw/` yet. |
| 2026-10-20 | 1 Cleanup | Codex docs, skills, logs, i18n and manual-statistics UI moved to `_archive_codex/` (git-ignored). Kept datasets/analysis/plotting/contracts/state. |
| 2026-10-20 | 2-4 Agent core | New tools.py, validation.py, llm.py (DeepSeek + FakeLLM), controller.py, runlog.py. `tests/test_agent.py`: 15 passed offline (FakeLLM). Old module tests not re-run here (no pytest in sandbox); run `python -m pytest -q` on Windows. |
| 2026-10-20 | 5 UI | New `app.py` (upload, question, mode, answer/table/chart/action log, labelled offline demo). Offline demo simulated in all 3 modes: baseline tool_error; raw_retry and proposed repair once and draw the chart. Not yet opened in a browser (no Streamlit in sandbox). New English README. |
| 2026-10-20 | 6 Evaluation set | `evaluation/`: 40 formal + 10 dev tasks (tasks.json), column notes, independent Pandas references, scorer, 10 fault cases + injector, resumable runner, metrics/charts. Data: train.csv 891 rows (sha256 7d118fef…), day.csv 731 rows (sha256 a6bcf826…). Oracle cross-check: tools and references agree on all 50 tasks; all 10 faults trigger; a corrupted reference is rejected. Runner + metrics tested end to end with FakeLLM. |
| 2026-10-20 | 7 Smoke run | Pending (sandbox has no internet; run on Windows). Model switched to `deepseek-flash` with thinking disabled after checking the official docs (deepseek-chat no longer listed). Price check 2026-10-20: $0.15 per 1M input tokens (cache miss, off-peak), $0.60 per 1M output. |
| 2026-10-20 | 8 Formal runs | Ran on Windows: 360 natural runs (results/formal.jsonl) and 90 fault runs (results/faults.jsonl); no API errors. |
| 2026-10-20 | 9 Analysis | Natural success 100% in all modes (one organic tool error in 360 runs). Fault recovery: baseline 10%, raw_retry 93.3%, proposed 100%; proposed needs 26% fewer tokens and 25% less time than raw_retry on faults. See results/analysis.md and results/figures/ (regenerate: python -m evaluation.figures). |
