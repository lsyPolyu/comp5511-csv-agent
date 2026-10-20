"""Dataset-aware validation used only by the proposed mode.

Before a tool runs, check the arguments against the *current* data: do the
columns exist, does the operation fit the column type, do category values
occur, does the result_id belong to this run. On a problem, return structured
feedback (what failed, what was requested, what is available). The program
never rewrites the call itself; the model decides how to revise it.
"""

from __future__ import annotations

import difflib

from pydantic import ValidationError

from comp5511.contracts import AggregateRequest, PlotRequest
from comp5511.state import AnalysisSession
from comp5511.tools import parse_arguments

MAX_MATCHES = 5
MAX_VALUES = 20
NUMERIC_OPS = ("gt", "ge", "lt", "le")


def close_matches(word, options) -> list:
    """Case-insensitive near matches, exact case-insensitive match first."""
    if not isinstance(word, str):
        return []
    lowered = {option.lower(): option for option in options}
    found = [lowered[word.lower()]] if word.lower() in lowered else []
    for match in difflib.get_close_matches(word.lower(), list(lowered), n=MAX_MATCHES, cutoff=0.5):
        if lowered[match] not in found:
            found.append(lowered[match])
    for option in options:  # substring hints, e.g. "class" -> "Pclass"
        if len(word) >= 3 and word.lower() in option.lower() and option not in found:
            found.append(option)
    return found[:MAX_MATCHES]


def _issue(code, field, requested, message, **context) -> dict:
    return {"code": code, "field": field, "requested": requested, "message": message,
            "error_stage": "dataset_validation", **context}


def _schema_issue(exc: ValidationError, hint: str) -> dict:
    first = exc.errors(include_input=False)[0]
    field = ".".join(str(part) for part in first["loc"]) or "arguments"
    return _issue("INVALID_ARGUMENTS", field, None, first["msg"], hint=hint)


def _column_info(session: AnalysisSession):
    dataset = session.dataset
    types = dict(zip(dataset.headers, dataset.logical_types))
    return types, list(dataset.headers)


def _categories(session: AnalysisSession, column: str) -> list:
    index = session.dataset.headers.index(column)
    seen = []
    for row in session.dataset._typed_rows:
        value = row[index]
        if value is not None and value not in seen:
            seen.append(value)
    return seen


def _check_column(name, field, types, columns):
    if name in types:
        return None
    return _issue("UNKNOWN_COLUMN", field, name, f"Column '{name}' does not exist in the current dataset.",
                  available_columns=columns, close_matches=close_matches(name, columns))


def _validate_aggregate(arguments: dict, session: AnalysisSession):
    try:
        request = AggregateRequest.model_validate(arguments)
    except ValidationError as exc:
        return _schema_issue(exc, "Expected {filters: [...], group_by: [...], metrics: [{operation, column, alias}], "
                                  "sort_by: [...]}. operation is row_count, count, sum or mean.")
    types, columns = _column_info(session)
    numeric = [name for name in columns if types[name] == "numeric"]
    for index, name in enumerate(request.group_by):
        issue = _check_column(name, f"group_by.{index}", types, columns)
        if issue:
            return issue
    for index, metric in enumerate(request.metrics):
        field = f"metrics.{index}.column"
        if metric.column is None:
            continue
        issue = _check_column(metric.column, field, types, columns)
        if issue:
            return issue
        if metric.operation in ("sum", "mean") and types[metric.column] != "numeric":
            return _issue("INCOMPATIBLE_OPERATION", field,
                          {"operation": metric.operation, "column": metric.column},
                          f"'{metric.operation}' needs a numeric column, but '{metric.column}' is "
                          f"{types[metric.column]}.",
                          allowed_operations_for_column=["row_count", "count"], numeric_columns=numeric)
    for index, condition in enumerate(request.filters):
        field = f"filters.{index}"
        issue = _check_column(condition.column, f"{field}.column", types, columns)
        if issue:
            return issue
        column_type = types[condition.column]
        values = condition.value if isinstance(condition.value, list) else [condition.value]
        if condition.op in NUMERIC_OPS and column_type != "numeric":
            return _issue("INCOMPATIBLE_FILTER", f"{field}.op", condition.op,
                          f"'{condition.op}' needs a numeric column, but '{condition.column}' is {column_type}.",
                          allowed_ops=["eq", "ne", "in"])
        if (condition.op == "in") != isinstance(condition.value, list):
            return _issue("INVALID_FILTER_VALUE", f"{field}.value", condition.value,
                          "Use a list of values with 'in' and a single value with the other operators.")
        if column_type == "numeric":
            bad = [value for value in values if type(value) not in (int, float)]
            if bad:
                return _issue("FILTER_TYPE_MISMATCH", f"{field}.value", condition.value,
                              f"Column '{condition.column}' is numeric; give numbers, not strings.",
                              example_values=_categories(session, condition.column)[:MAX_VALUES])
        elif column_type == "text":
            bad = [value for value in values if not isinstance(value, str)]
            if bad:
                return _issue("FILTER_TYPE_MISMATCH", f"{field}.value", condition.value,
                              f"Column '{condition.column}' is text; give values as strings.",
                              valid_values=_categories(session, condition.column)[:MAX_VALUES])
            categories = _categories(session, condition.column)
            missing = [value for value in values if value not in categories]
            if missing and condition.op in ("eq", "in"):
                return _issue("UNKNOWN_CATEGORY", f"{field}.value", missing[0],
                              f"Value '{missing[0]}' never occurs in column '{condition.column}'.",
                              valid_values=categories[:MAX_VALUES],
                              close_matches=close_matches(missing[0], [str(c) for c in categories]))
    return None


def _validate_plot(arguments: dict, session: AnalysisSession):
    available = session.result_summaries()
    result_id = arguments.get("result_id")
    match = next((item for item in available if item["result_id"] == result_id), None)
    if match is None:
        return _issue("UNKNOWN_RESULT", "result_id", result_id,
                      "This result_id is not a successful aggregate_data result of the current task.",
                      available_results=available)
    for name in ("x", "y"):
        if name in arguments and arguments[name] not in match["fields"]:
            return _issue("UNKNOWN_FIELD", name, arguments[name],
                          f"Field '{arguments[name]}' is not in result {result_id}.",
                          available_fields=match["fields"],
                          close_matches=close_matches(arguments[name], match["fields"]))
    try:
        PlotRequest.model_validate(arguments)
    except ValidationError as exc:
        return _schema_issue(exc, "Required: result_id, chart_type ('bar' or 'line'), x, y, title, x_label, "
                                  "y_label. For percent display use y_format='percent', unit='fraction' and a "
                                  "y_label containing '(%)'. Line charts need a numeric x.")
    source = session.resolve_result(result_id)["data"]
    types = {field["name"]: field["logical_type"] for field in source["fields"]}
    if types.get(arguments["y"]) != "numeric":
        return _issue("INCOMPATIBLE_PLOT", "y", arguments["y"], "The y field must be numeric.",
                      numeric_fields=[name for name, kind in types.items() if kind == "numeric"])
    if arguments.get("chart_type") == "line" and arguments.get("x_kind") in (None, "numeric") \
            and types.get(arguments["x"]) != "numeric":
        return _issue("INCOMPATIBLE_PLOT", "x", arguments["x"],
                      "Line charts need a numeric x field (or x_kind='date' for YYYY-MM-DD text). "
                      "Use chart_type='bar' for categories.")
    return None


def validate(name: str, raw_arguments, session: AnalysisSession) -> dict | None:
    """Return None if the call may run, otherwise one structured issue."""
    arguments, failure = parse_arguments(raw_arguments)
    if failure:
        return _issue("INVALID_JSON", "arguments", None, failure["error"]["message"],
                      hint="Send the arguments as one JSON object.")
    if session.dataset is None:
        return None  # the shared NO_DATASET error from the tool is clear enough
    if name == "aggregate_data":
        return _validate_aggregate(arguments, session)
    if name == "plot_result":
        return _validate_plot(arguments, session)
    return None


def feedback_envelope(issue: dict) -> dict:
    return {"success": False, "data": None, "warnings": [], "error": issue}
