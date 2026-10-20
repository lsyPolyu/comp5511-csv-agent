"""Inspect and aggregate one CSV locally, without a model or API credentials."""

import pandas as pd
import streamlit as st

from comp5511.datasets import DatasetError, inspect_dataset, load_csv
from comp5511.chart_ui import render_charts
from comp5511.i18n import LANGUAGES, message_text, option_label, text
from comp5511.state import AnalysisSession
from comp5511.statistics_ui import render_statistics


def _clear_current_upload() -> None:
    """Invalidate the old dataset before processing any changed upload."""
    session = st.session_state.get("_analysis_state")
    if session is not None:
        session.clear_dataset()
    for key in list(st.session_state):
        if key.startswith(("stats_", "chart_")):
            st.session_state.pop(key, None)
    for key in ("_dataset", "_load_error", "_handled_upload_id", "_statistics_error", "_chart_error", "_chart_source_id"):
        st.session_state.pop(key, None)


def _sync_localized_options(language: str) -> None:
    """Send fresh display strings while retaining the selected enum values."""
    if st.session_state.get("_ui_options_language") == language:
        return
    # Streamlit serializes formatted options as display strings. Reassigning
    # the unchanged internal value makes it emit set_value/raw_value using
    # the new formatter, so the next client request cannot replay old labels.
    for key in list(st.session_state):
        if key.startswith(("stats_operation_", "stats_filter_op_", "stats_sort_direction_", "stats_column_")) or key in (
            "chart_type", "chart_x_kind", "chart_y_format",
        ):
            st.session_state[key] = st.session_state[key]
    st.session_state["_ui_options_language"] = language


language = st.session_state.get("ui_language", "en")
st.set_page_config(page_title=text("COMP5511 CSV Inspector", language), layout="wide")
language = st.radio("English / 中文", LANGUAGES, key="ui_language", horizontal=True,
                    format_func=lambda value: "English" if value == "en" else "中文")
_sync_localized_options(language)
st.title(text("CSV Dataset Inspector", language))
st.caption(text("Local tools only. No API key or model is used.", language))
st.write(text(
    "Upload one comma-separated CSV with a header, encoded as UTF-8 or UTF-8-BOM. "
    "Limits: 20 MiB and 100,000 data rows. Only empty fields count as missing.", language
))

# Session state is local to the connected browser session, never a global cache.
# https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
if "_analysis_state" not in st.session_state:
    session = AnalysisSession()
    # Preserve an already loaded P01 upload when this page reloads after upgrade.
    previous_dataset = st.session_state.pop("_dataset", None)
    if previous_dataset is not None:
        session.replace_dataset(previous_dataset)
    st.session_state["_analysis_state"] = session
elif not isinstance(st.session_state["_analysis_state"], AnalysisSession):
    # Streamlit can retain an instance of the P02 class across module reloads.
    previous_session = st.session_state["_analysis_state"]
    session = AnalysisSession()
    session.__dict__.update(previous_session.__dict__)
    st.session_state["_analysis_state"] = session
analysis_session = st.session_state["_analysis_state"]

# Validate the extension locally too, so an invalid replacement clears old data.
uploaded = st.file_uploader(
    text("Upload a CSV file", language), accept_multiple_files=False, key="csv_upload",
    help=text("Choose Browse files to select a CSV, or drag one into the upload area.", language),
    on_change=_clear_current_upload,
)
upload_id = uploaded.file_id if uploaded is not None else None
if upload_id != st.session_state.get("_handled_upload_id"):
    _clear_current_upload()
    st.session_state["_handled_upload_id"] = upload_id
    if uploaded is not None:
        try:
            analysis_session.replace_dataset(load_csv(uploaded.getvalue(), uploaded.name))
        except DatasetError as exc:
            st.session_state["_load_error"] = {"code": exc.code, "message": exc.message}

error = st.session_state.get("_load_error")
dataset = analysis_session.dataset
if error:
    if isinstance(error, str):
        # Existing live sessions may still hold the pre-i18n formatted error.
        code, _, message = error.partition(": ")
        error = {"code": code, "message": message}
    st.error(message_text(error, language))
    st.info(text("No current dataset. Select another CSV to continue.", language))
elif dataset is None:
    st.info(text("Select a CSV file to inspect its real data.", language))
else:
    result = inspect_dataset(dataset)
    if not result["success"]:
        st.error(message_text(result["error"], language))
    else:
        summary = result["data"]
        st.success(text("CSV loaded and inspected locally.", language))
        st.caption(text("Dataset ID: {dataset_id}", language, dataset_id=summary["dataset_id"]))
        rows, columns = st.columns(2)
        rows.metric(text("Rows", language), summary["row_count"])
        columns.metric(text("Columns", language), len(summary["columns"]))
        st.subheader(text("Preview (first 5 rows)", language))
        st.dataframe(pd.DataFrame(summary["preview"], dtype=object), hide_index=True)
        st.subheader(text("Column summary", language))
        st.dataframe(
            pd.DataFrame([
                {
                    text("Column", language): column["name"],
                    text("Logical type", language): option_label(column["logical_type"], language),
                    text("Missing count", language): column["missing_count"],
                    text("Missing ratio", language): column["missing_ratio"],
                }
                for column in summary["columns"]
            ]),
            hide_index=True,
            column_config={
                text("Missing ratio", language): st.column_config.NumberColumn(format="%.4f"),
            },
        )
        st.caption(text("Missing ratio = missing count / row count. Preview is limited to 5 rows.", language))
        render_statistics(analysis_session, language=language)
        render_charts(analysis_session, language=language)
