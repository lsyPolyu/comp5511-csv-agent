"""Localized chart controls over the current registered statistics result."""

import pandas as pd
import streamlit as st

from comp5511.plotting import plot_result
from comp5511.i18n import chart_defaults, message_text, option_label, text
from comp5511.state import AnalysisSession


def _reset_controls() -> None:
    for key in list(st.session_state):
        if key.startswith("chart_"):
            st.session_state.pop(key, None)
    st.session_state.pop("_chart_error", None)
    st.session_state.pop("_chart_default_values", None)
    st.session_state.pop("_chart_custom_fields", None)


def _mark_custom(key: str) -> None:
    st.session_state.setdefault("_chart_custom_fields", set()).add(key)


def _sync_defaults(language: str) -> None:
    defaults = chart_defaults(language)
    if st.session_state.get("chart_y_format") == "percent":
        defaults["chart_y_label"] += " (%)"
    previous = st.session_state.get("_chart_default_values", chart_defaults("en"))
    custom = st.session_state.setdefault("_chart_custom_fields", set())
    for key, value in defaults.items():
        if key not in st.session_state or (key not in custom and st.session_state[key] == previous[key]):
            st.session_state[key] = value
        else:
            # Preserve custom text, including text from pre-i18n live sessions.
            custom.add(key)
    st.session_state["_chart_default_values"] = defaults


def render_charts(session: AnalysisSession, language: str = "en") -> None:
    result = session.current_result()
    result_id = result["data"]["result_id"] if result is not None else None
    if st.session_state.get("_chart_source_id") != result_id:
        _reset_controls()
        st.session_state["_chart_source_id"] = result_id
    if result is None:
        return
    _sync_defaults(language)
    source = result["data"]
    names = [field["name"] for field in source["fields"]]
    numeric = [field["name"] for field in source["fields"] if field["logical_type"] == "numeric"]
    measures = [field["name"] for field in source["fields"] if field["role"] == "metric" and field["logical_type"] == "numeric"]
    st.subheader(text("Chart from statistics", language))
    st.caption(text("Source result: {result_id}. Generating or downloading a chart does not rerun statistics.", language, result_id=result_id))
    # Synchronize edits for language changes; only the explicit button renders.
    with st.container():
        st.selectbox(text("Source result", language), [result_id], key="chart_source")
        columns = st.columns(3)
        chart_type = columns[0].selectbox(text("Chart type", language), ["bar", "line"], format_func=lambda value: option_label(value, language), key="chart_type")
        x = columns[1].selectbox(text("X field", language), names, key="chart_x")
        default_y = (measures or numeric or names)[0]
        y = columns[2].selectbox(text("Y field", language), names, index=names.index(default_y), key="chart_y")
        title = st.text_input(text("Chart title", language), key="chart_title", on_change=_mark_custom, args=("chart_title",))
        labels = st.columns(2)
        x_label = labels[0].text_input(text("X-axis label", language), key="chart_x_label", on_change=_mark_custom, args=("chart_x_label",))
        y_label = labels[1].text_input(text("Y-axis label", language), help=text("For percent display, include (%) or (percent).", language), key="chart_y_label", on_change=_mark_custom, args=("chart_y_label",))
        types = st.columns(2)
        x_kind = types[0].selectbox(text("X kind", language), ["default", "category", "numeric", "date"], format_func=lambda value: option_label(value, language), help=text("Default: category for bar, numeric for line. Line charts require numeric or date.", language), key="chart_x_kind")
        date_format = types[1].text_input(text("Date format", language), help=text("Enter %Y-%m-%d only when X kind is date; leave empty otherwise.", language), key="chart_date_format")
        formats = st.columns(3)
        y_format = formats[0].selectbox(text("Y format", language), ["number", "percent"], format_func=lambda value: option_label(value, language), key="chart_y_format")
        decimals = formats[1].number_input(text("Decimal places", language), min_value=0, max_value=6, value=2, key="chart_decimals")
        unit = formats[2].text_input(text("Unit", language), value="unknown", help=text("Use fraction for percent. Otherwise specify an English unit or unknown.", language), key="chart_unit")
        submitted = st.button(text("Generate chart", language), key="chart_submit", type="primary")
    if submitted:
        arguments = {"result_id": result_id, "chart_type": chart_type, "x": x, "y": y, "title": title,
                     "x_label": x_label, "y_label": y_label, "y_format": y_format,
                     "decimal_places": decimals, "unit": unit}
        if x_kind != "default":
            arguments["x_kind"] = x_kind
        if date_format:
            arguments["date_format"] = date_format
        response = plot_result(session, arguments)
        st.session_state["_chart_error"] = response["error"]
    error = st.session_state.get("_chart_error")
    if error:
        st.error(message_text(error, language))
    current = session.current_chart()
    if current is None:
        return
    chart = current["data"]
    png = session.chart_bytes(chart["chart_id"])
    if png is None:
        return
    st.caption(text("Last successful chart: {chart_id} | Result: {result_id} | Run: {run_id}", language,
                    chart_id=chart["chart_id"], result_id=chart["result_id"], run_id=chart["run_id"]))
    for warning in current["warnings"]:
        st.warning(message_text(warning, language))
    st.image(png, caption=chart["title"], width="stretch", alt=chart["title"])
    # Ignore click reruns; the downloaded bytes are exactly the registered PNG.
    # https://docs.streamlit.io/develop/api-reference/widgets/st.download_button
    st.download_button(text("Download chart (PNG)", language), png, file_name=chart["artifact"]["filename"], mime="image/png", key="chart_download", on_click="ignore")
    st.subheader(text("Underlying plot data", language))
    st.dataframe(pd.DataFrame(chart["plot_data"], dtype=object), hide_index=True,
                 column_config={key: text(label, language) for key, label in {
                     "source_index": "Source index", "x": "Original X", "y": "Original Y",
                     "x_sort_key": "X sort key", "display_x": "Display X", "display_y": "Display Y",
                 }.items()})
    with st.expander(text("Chart source and format", language)):
        st.json({key: value for key, value in chart.items() if key != "plot_data"})

