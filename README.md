# CSV Analysis Agent (COMP5511 project)

A tool-using agent that answers questions about one uploaded CSV file. An LLM (DeepSeek, via
tool calling) chooses among three predefined tools — `inspect_dataset`, `aggregate_data`,
`plot_result` — and local Python code does every calculation. The project compares three ways of
handling a failed tool call:

| Mode | After a tool call fails |
| --- | --- |
| `baseline` | stop (status `tool_error`) |
| `raw_retry` | return the raw error text; up to 2 repair rounds |
| `proposed` | dataset-aware validation before execution; structured feedback (available columns, close matches, valid values); up to 2 repair rounds |

## Setup (Windows PowerShell)

```powershell
cd F:\JavaAiNew\agent_project\COMP5511
py -3.12 -m venv .venv                      # skip if .venv already exists
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
copy .env.example .env                      # then put your key in .env: DEEPSEEK_API_KEY=...
```

## Run

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py     # web UI at http://localhost:8501
.\.venv\Scripts\python.exe -m pytest -q                # offline tests (no API key needed)
```

Without an API key, tick "Offline scripted demo" in the UI and use the 8-row sample: it replays a
fixed script (a wrong column, feedback, a fix, a chart) and is labelled as offline.

## Reproduce the experiments

Put Kaggle Titanic `train.csv` and UCI Bike Sharing `day.csv` in `data\raw\` (expected SHA-256 prefixes
7d118fef and a6bcf826), then:

```powershell
.\.venv\Scripts\python.exe -m evaluation.runner --split dev --repeats 1 --out results\smoke.jsonl     # 30 runs
.\.venv\Scripts\python.exe -m evaluation.runner --split formal --repeats 3 --out results\formal.jsonl # 360 runs
.\.venv\Scripts\python.exe -m evaluation.runner --faults --repeats 3 --out results\faults.jsonl      # 90 runs
.\.venv\Scripts\python.exe -m evaluation.metrics --natural results\formal.jsonl --faults results\faults.jsonl
.\.venv\Scripts\python.exe -m evaluation.figures                                                     # report figures
```

The runner resumes: re-running a command skips finished runs. The logged runs of the reported
experiment are in `results\` (model deepseek-flash, thinking disabled, temperature 0, 2026-10-20);
`results\analysis.md` summarises them.

## Layout

- `comp5511/datasets.py` CSV loading and summary · `analysis.py` filters, grouping, statistics ·
  `plotting.py` charts from registered results · `contracts.py` argument models
- `comp5511/tools.py` tool specs and whitelist dispatcher · `validation.py` dataset-aware checks ·
  `llm.py` DeepSeek client and FakeLLM · `controller.py` agent loop and counters · `runlog.py` JSONL logs
- `app.py` Streamlit UI · `tests/` offline tests · `evaluation/` experiments (in progress)

Rules that are fixed for the experiments are listed in `AGENTS.md`.

## Acknowledgements

Built with Python, Streamlit, Pandas, Matplotlib, Pydantic, httpx and the DeepSeek API.
Code was written with AI assistance (OpenAI Codex and Anthropic Claude) and reviewed by the author.
Datasets: Kaggle Titanic (train.csv) and UCI Bike Sharing (day.csv, doi:10.24432/C5W894).
