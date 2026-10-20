# COMP5511 CSV analysis agent — rules for any coding assistant

Plan: see the "COMP5511 项目规划" doc. Proposal and course spec are in the repo root.

Fixed rules (do not change without the owner's approval; frozen before formal runs):
- One CSV per task; only three whitelisted tools: inspect_dataset, aggregate_data, plot_result. No eval/exec.
- Three modes share model, system prompt, tool specs and budgets; they differ only after a tool fails:
  baseline stops; raw_retry returns the raw error; proposed validates first and returns structured feedback.
- T <= 8 tool attempts per task (failures count; calls skipped after a failure in the same response do not).
- R <= 2 repair rounds: the first model response after a failure is one round, whatever it does.
- Max 12 model requests, 60 s HTTP timeout, 2 network retries (not repairs), 180 s per task.
- Missing value = empty field. count = non-missing values; row_count = rows; sum/mean skip missing.
- The program never rewrites the model's arguments; it only gives feedback.
- API key only from .env (DEEPSEEK_API_KEY); never in code, logs or Git.
- Reference answers (evaluation/references.py) must not import any agent tool.

Layout: comp5511/ (datasets, analysis, plotting, contracts, state, tools, validation, llm, controller, runlog),
app.py (Streamlit), evaluation/ (tasks, references, scoring, faults, runner, metrics), tests/.
Progress: docs/progress.md (one line per stage). Run tests: python -m pytest -q
