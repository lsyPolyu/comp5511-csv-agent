# Progress

| Date | Stage | Result |
| --- | --- | --- |
| 2026-10-20 | 0 Preflight | Git snapshot `76c74e8`. The linked computer's sandbox and the cloud sandbox have no internet (PyPI, DeepSeek, UCI unreachable); no `.env`, no `data/raw/` yet. |
| 2026-10-20 | 1 Cleanup | Codex docs, skills, logs, i18n and manual-statistics UI moved to `_archive_codex/` (git-ignored). Kept datasets/analysis/plotting/contracts/state. |
| 2026-10-20 | 2-4 Agent core | New tools.py, validation.py, llm.py (DeepSeek + FakeLLM), controller.py, runlog.py. `tests/test_agent.py`: 15 passed offline (FakeLLM). Old module tests not re-run here (no pytest in sandbox); run `python -m pytest -q` on Windows. |
| 2026-10-20 | 5 UI | New `app.py` (upload, question, mode, answer/table/chart/action log, labelled offline demo). Offline demo simulated in all 3 modes: baseline tool_error; raw_retry and proposed repair once and draw the chart. Not yet opened in a browser (no Streamlit in sandbox). New English README. |
