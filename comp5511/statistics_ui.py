"""Local statistics controls; computation and ownership live in other modules."""

import math

import pandas as pd
import streamlit as st

from comp5511.analysis import aggregate_data
from comp5511.contracts import error_result
from comp5511.i18n import message_text, option_label, text
from comp5511.state import AnalysisSession


def _show_result(response: dict, language: str = "en") -> None:
    data = response["data"]
    st.subheader(text("Statistics result", language))
    st.caption(text("Showing the last submitted calculation. Editing controls does not run it again.", language))
    st.caption(text("Result ID: {result_id} | Dataset ID: {dataset_id} | Run ID: {run_id}", language,
                    result_id=data["result_id"], dataset_id=data["dataset_id"], run_id=data["run_id"]))
    st.write(text("Filtered rows: {count}", language, count=data["filtered_row_count"]))
    for warning in response["warnings"]:
        st.warning(message_text(warning, language))
    frame = pd.DataFrame(data["rows"], columns=[field["name"] for field in data["fields"]], dtype=object)
    # A missing key must not look like a real category with the same label.
    for name in data["group_by"]:
        if any(value is None for value in frame[name]):
            labels = {str(value) for value in frame[name] if value is not None}
            missing_label = "<missing>"
            while missing_label in labels:
                missing_label += " (null)"
            frame[name] = [missing_label if value is None else str(value) for value in frame[name]]
            st.caption(text("Missing group keys in {name!r} are displayed as {missing_label!r}.", language,
                            name=name, missing_label=missing_label))
    st.dataframe(frame, hide_index=True)
    with st.expander(text("Calculation details", language)):
        st.json({"fields": data["fields"], "operations": data["operations"]})


def render_statistics(session: AnalysisSession, language: str = "en") -> None:
    dataset = session.dataset
    if dataset is None:
        return
    st.subheader(text("Local statistics", language))
    st.write(text("Set the number of filter, metric and sort rows, then configure the form and click Run statistics.", language))
    filters_col, metrics_col, sorts_col = st.columns(3)
    filter_count = filters_col.number_input(text("Number of filters", language), min_value=0, max_value=10, value=0, key="stats_filter_count")
    metric_count = metrics_col.number_input(text("Number of metrics", language), min_value=1, max_value=10, value=1, key="stats_metric_count")
    sort_count = sorts_col.number_input(text("Number of sort keys", language), min_value=0, max_value=10, value=0, key="stats_sort_count")
    # Keyed widgets synchronize edits before a language rerun; only the button computes.
    with st.container():
        groups = st.multiselect(text("Group by", language), dataset.headers, key="stats_groups")
        filters = []
        for index in range(filter_count):
            st.markdown(text("**Filter {index} (all filters use AND)**", language, index=index + 1))
            column = st.selectbox(text("Filter column {index}", language, index=index + 1), dataset.headers, key=f"stats_filter_column_{index}")
            op = st.selectbox(text("Filter operator {index}", language, index=index + 1), ["eq", "ne", "gt", "ge", "lt", "le", "in"], format_func=lambda value: option_label(value, language), key=f"stats_filter_op_{index}")
            value = st.text_area(text("Filter value {index}", language, index=index + 1), help=text("For in, enter one value per line. Otherwise enter one value. Numeric columns require finite numbers; text stays literal.", language), key=f"stats_filter_value_{index}")
            filters.append({"column": column, "op": op, "value": value})
        st.caption(text("row_count counts rows and uses No column. count counts nonmissing values. sum and mean require a numeric column. Aliases must be unique.", language))
        metrics = []
        for index in range(metric_count):
            cells = st.columns(3)
            operation = cells[0].selectbox(text("Operation {index}", language, index=index + 1), ["row_count", "count", "sum", "mean"], format_func=lambda value: option_label(value, language), key=f"stats_operation_{index}")
            column = cells[1].selectbox(text("Column {index}", language, index=index + 1), [None, *dataset.headers], format_func=lambda name: option_label(None, language) if name is None else name, key=f"stats_column_{index}")
            alias = cells[2].text_input(text("Alias {index}", language, index=index + 1), value="rows" if index == 0 else f"metric_{index + 1}", key=f"stats_alias_{index}")
            metrics.append({"operation": operation, "column": column, "alias": alias})
        sorts = []
        for index in range(sort_count):
            cells = st.columns(2)
            column = cells[0].text_input(text("Sort field {index}", language, index=index + 1), help=text("Enter an exact grouping column name or metric alias. Keys are applied in this order; missing values are always last.", language), key=f"stats_sort_field_{index}")
            direction = cells[1].selectbox(text("Sort direction {index}", language, index=index + 1), ["asc", "desc"], format_func=lambda value: option_label(value, language), key=f"stats_sort_direction_{index}")
            sorts.append({"column": column, "direction": direction})
        submitted = st.button(text("Run statistics", language), key="stats_submit", type="primary")
    if submitted:
        run_id = session.begin_run()
        try:
            filters = _parse_filters(filters, dict(zip(dataset.headers, dataset.logical_types)))
        except ValueError:
            response = error_result("INVALID_FILTER_TYPE", "Enter finite numbers for numeric filters. For in, put one value on each line.", "filters")
        else:
            response = aggregate_data(dataset, {"filters": filters, "group_by": groups, "metrics": metrics, "sort_by": sorts}, session_id=session.session_id, run_id=run_id)
        response = session.publish_result(response)
        st.session_state["_statistics_error"] = response["error"]
    error = st.session_state.get("_statistics_error")
    if error:
        st.error(message_text(error, language))
    current = session.current_result()
    if current is not None:
        _show_result(current, language)


def _parse_filters(filters: list[dict], types: dict[str, str]) -> list[dict]:
    """Convert form text to typed values without evaluating user expressions."""
    parsed = []
    for condition in filters:
        values = condition["value"].splitlines() if condition["op"] == "in" else [condition["value"]]
        if types[condition["column"]] == "numeric":
            values = [float(value) for value in values]
            if any(not math.isfinite(value) for value in values):
                raise ValueError("Numeric filter values must be finite.")
        parsed.append({**condition, "value": values if condition["op"] == "in" else values[0]})
    return parsed
