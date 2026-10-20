"""Streamlit UI: upload a CSV, ask a question, watch the agent use its tools.

Run on Windows:  .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from comp5511.controller import AgentConfig, MODES, run_agent
from comp5511.datasets import DatasetError, inspect_dataset, load_csv
from comp5511.llm import DeepSeekClient, FakeLLM, LLMError
from comp5511.state import AnalysisSession

load_dotenv()
SAMPLE = Path(__file__).parent / "data" / "dev" / "eight_rows.csv"
MODE_HELP = {
    "baseline": "Stops at the first failed tool call.",
    "raw_retry": "Sends the raw error back; up to 2 repair rounds.",
    "proposed": "Validates against the data first; structured feedback; up to 2 repair rounds.",
}

st.set_page_config(page_title="CSV Analysis Agent", layout="wide")
st.title("CSV Analysis Agent")
st.caption("An LLM chooses predefined tools; all numbers are computed locally by Python.")

if "analysis" not in st.session_state:
    st.session_state.analysis = AnalysisSession()
    st.session_state.last_run = None
    st.session_state.upload_id = None
session: AnalysisSession = st.session_state.analysis


def _offline_demo_llm():
    """Scripted run for the 8-row sample: a wrong column, feedback, a fix, a chart."""
    bad = {"group_by": ["gender"], "metrics": [{"operation": "mean", "column": "Survived", "alias": "survival_rate"}]}
    good = {"group_by": ["Sex"], "metrics": [{"operation": "mean", "column": "Survived", "alias": "survival_rate"}]}

    def plot(messages):
        result_id = json.loads(messages[-1]["content"])["result_id"]
        return [("plot_result", {"result_id": result_id, "chart_type": "bar", "x": "Sex", "y": "survival_rate",
                                 "title": "Survival rate by sex", "x_label": "Sex",
                                 "y_label": "Survival rate (%)", "y_format": "percent", "unit": "fraction"})]

    return FakeLLM([[("aggregate_data", bad)], [("aggregate_data", good)], plot,
                    "Survival rate: female 0.75, male 0.25 (offline scripted demo)."], model="offline-demo")


# ---------- data ----------
left, right = st.columns([2, 1])
uploaded = left.file_uploader("Upload one CSV file (UTF-8, header row)", type=["csv"])
if right.button("Use the 8-row sample"):
    uploaded = None
    session.replace_dataset(load_csv(SAMPLE.read_bytes(), SAMPLE.name))
    st.session_state.upload_id, st.session_state.last_run = "sample", None
if uploaded is not None and uploaded.file_id != st.session_state.upload_id:
    st.session_state.upload_id, st.session_state.last_run = uploaded.file_id, None
    try:
        session.replace_dataset(load_csv(uploaded.getvalue(), uploaded.name))
    except DatasetError as exc:
        session.clear_dataset()
        st.error(f"{exc.code}: {exc.message}")

if session.dataset is None:
    st.info("Upload a CSV or use the sample to start.")
    st.stop()

summary = inspect_dataset(session.dataset)["data"]
with st.expander(f"Data: {summary['row_count']} rows, {len(summary['columns'])} columns", expanded=False):
    st.dataframe(pd.DataFrame(summary["preview"], dtype=object), hide_index=True)
    st.dataframe(pd.DataFrame([{k: c[k] for k in ("name", "logical_type", "missing_count")}
                               for c in summary["columns"]]), hide_index=True)

# ---------- question ----------
with st.form("ask"):
    question = st.text_input("Question (English)", "What was the survival rate by sex? Draw a bar chart.")
    mode = st.radio("Mode", MODES, index=2, horizontal=True, format_func=lambda m: m,
                    help="\n".join(f"{m}: {h}" for m, h in MODE_HELP.items()))
    offline = st.checkbox("Offline scripted demo (no API call; only for the 8-row sample)")
    submitted = st.form_submit_button("Run")

if submitted:
    try:
        llm = _offline_demo_llm() if offline else DeepSeekClient()
        with st.spinner("Agent is working..."):
            run = run_agent(question, session, llm, AgentConfig(mode=mode))
        st.session_state.last_run = run  # stored so reruns never call the model again
    except LLMError as exc:
        st.error(f"Model client error: {exc}")

run = st.session_state.last_run
if run is None:
    st.stop()

# ---------- result ----------
status_text = f"Status: **{run.status}** · mode {run.mode} · model {run.model}"
(st.success if run.status == "completed" else st.warning)(status_text)
if run.answer:
    st.markdown(f"**Answer:** {run.answer}")
metrics = st.columns(5)
metrics[0].metric("Tool calls (T)", f"{run.tool_calls} / 8")
metrics[1].metric("Repairs (R)", f"{run.repairs} / 2")
metrics[2].metric("Model requests", run.model_requests)
metrics[3].metric("Latency (s)", run.latency_s)
metrics[4].metric("Tokens", "unknown" if run.prompt_tokens is None else run.prompt_tokens + run.completion_tokens)

table_col, chart_col = st.columns(2)
if run.result_ids:
    result = session.resolve_result(run.result_ids[-1])
    if result["success"]:
        table_col.subheader("Result table")
        table_col.dataframe(pd.DataFrame(result["data"]["rows"]), hide_index=True)
if run.chart_id:
    png = session.chart_bytes(run.chart_id)
    if png:
        chart_col.subheader("Chart")
        chart_col.image(png)
        chart_col.download_button("Download PNG", png, file_name=f"{run.chart_id}.png", mime="image/png")

st.subheader("Action log")
for step in run.steps:
    if step["type"] == "model":
        label = "repair round" if step["repair_round"] else "model request"
        detail = ", ".join(step["tool_calls"]) or "text answer"
        st.markdown(f"🧠 **{label} {step['request']}** → {detail}")
    elif "skipped" in step:
        st.markdown(f"⏭️ `{step['name']}` skipped ({step['skipped']})")
    else:
        icon = "✅" if step["success"] else "❌"
        st.markdown(f"{icon} `{step['name']}` (T={step['T']})")
        st.code(step["arguments"], language="json")
        if step.get("injected"):
            st.caption(f"Injected fault: {step['injected']}")
        if not step["success"]:
            st.caption(f"Error {step['error']['code']} at {step['error']['field']}: {step['error']['message']}")
