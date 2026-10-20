"""Tool definitions for the model and a whitelist dispatcher.

The model only *requests* a tool call (a name plus JSON arguments). This module
decides whether the name is allowed, parses the arguments and runs the matching
local Python function. No model output is ever executed as code.
"""

from __future__ import annotations

import json
from copy import deepcopy

from comp5511.analysis import aggregate_data
from comp5511.contracts import AggregateRequest, PlotRequest, error_result
from comp5511.datasets import inspect_dataset
from comp5511.plotting import plot_result
from comp5511.state import AnalysisSession

TOOL_NAMES = ("inspect_dataset", "aggregate_data", "plot_result")
MAX_ROWS_TO_MODEL = 50
SUMMARY_PREVIEW_ROWS = 3


def _inline_refs(schema: dict) -> dict:
    """Replace Pydantic "$ref" pointers with their definitions (simpler for the model)."""
    definitions = schema.get("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return resolve(deepcopy(definitions[name]))
            return {key: resolve(value) for key, value in node.items() if key != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def _schema(model) -> dict:
    schema = _inline_refs(model.model_json_schema())
    schema.pop("title", None)
    return schema


AGGREGATE_DESCRIPTION = (
    "Filter rows, optionally group them, and compute statistics on the current CSV. "
    "filters: list of {column, op, value}; op is one of eq, ne, gt, ge, lt, le, in; "
    "conditions are combined with AND; gt/ge/lt/le need a numeric column and a number; "
    "eq/ne/in values must have the column's type (text values are strings, numbers are numbers). "
    "group_by: list of column names (may be empty). "
    "metrics: list of {operation, column, alias}; operation is row_count (no column), "
    "count (non-missing values of column), sum or mean (numeric columns only, missing values skipped). "
    "The mean of a 0/1 column is a rate. alias names the output field. "
    "sort_by: optional list of {column, direction}, where column is a group_by column or an alias. "
    "Returns a result_id, the filtered row count and the result rows."
)

PLOT_DESCRIPTION = (
    "Draw a bar or line chart from an existing aggregate_data result. "
    "result_id must come from a successful aggregate_data call in this task; "
    "x and y are field names of that result (y must be numeric). "
    "title, x_label and y_label are required English text. "
    "Line charts need a numeric x (or a date x with x_kind='date' and date_format='%Y-%m-%d'). "
    "y_format may be 'number' (default) or 'percent'; percent requires unit='fraction' "
    "and a y_label containing '(%)'."
)

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "inspect_dataset",
        "description": "Return the column names, column types, missing-value counts, "
                       "category samples and a few preview rows of the current CSV.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "aggregate_data", "description": AGGREGATE_DESCRIPTION,
        "parameters": _schema(AggregateRequest),
    }},
    {"type": "function", "function": {
        "name": "plot_result", "description": PLOT_DESCRIPTION,
        "parameters": _schema(PlotRequest),
    }},
]


def dataset_summary(session: AnalysisSession) -> dict:
    """Compact inspect_dataset output that is safe to put into a prompt."""
    result = inspect_dataset(session.dataset)
    if not result["success"]:
        return result
    data = result["data"]
    return {
        "success": True,
        "row_count": data["row_count"],
        "columns": [
            {key: column[key] for key in ("name", "logical_type", "missing_count")}
            | ({"category_samples": column["category_samples"], "more_categories": column["truncated"]}
               if column["logical_type"] == "text" else {})
            for column in data["columns"]
        ],
        "preview": data["preview"][:SUMMARY_PREVIEW_ROWS],
    }


def parse_arguments(raw_arguments) -> tuple[dict | None, dict | None]:
    """Turn the model's raw JSON string into a dict, or return a structured error."""
    if isinstance(raw_arguments, dict):
        return raw_arguments, None
    try:
        arguments = json.loads(raw_arguments or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        return None, error_result("INVALID_JSON", f"Arguments are not valid JSON: {exc}", "arguments", "schema")
    if not isinstance(arguments, dict):
        return None, error_result("INVALID_JSON", "Arguments must be a JSON object.", "arguments", "schema")
    return arguments, None


def dispatch(name: str, raw_arguments, session: AnalysisSession) -> dict:
    """Run one whitelisted tool and return the unified envelope.

    Envelope: {"success", "data", "error", "warnings"}; error has code, field,
    message and error_stage. These basic checks are shared by every mode.
    """
    if name not in TOOL_NAMES:
        return error_result("UNKNOWN_TOOL", f"Unknown tool '{name}'.", "name", "schema")
    arguments, failure = parse_arguments(raw_arguments)
    if failure:
        return failure
    try:
        if name == "inspect_dataset":
            if arguments:
                return error_result("INVALID_ARGUMENTS", "inspect_dataset takes no arguments.", "arguments", "schema")
            summary = dataset_summary(session)
            if not summary.get("success"):
                return summary
            return {"success": True, "data": summary, "error": None, "warnings": []}
        if name == "aggregate_data":
            response = aggregate_data(session.dataset, arguments,
                                      session_id=session.session_id, run_id=session.run_id or "")
            return session.publish_result(response)
        return plot_result(session, arguments)
    except Exception as exc:  # a tool bug must not crash the agent loop
        return error_result("EXECUTION_ERROR", f"{type(exc).__name__}: {exc}", None, "execution")


def result_for_model(name: str, envelope: dict) -> dict:
    """Shrink a tool envelope to what the model needs to see next."""
    if not envelope.get("success"):
        return {"success": False, "error": envelope.get("error")}
    data = envelope["data"]
    if name == "inspect_dataset":
        return {key: value for key, value in data.items() if key != "success"} | {"success": True}
    if name == "aggregate_data":
        rows = data["rows"]
        return {
            "success": True, "result_id": data["result_id"],
            "filtered_row_count": data["filtered_row_count"],
            "fields": [field["name"] for field in data["fields"]],
            "rows": rows[:MAX_ROWS_TO_MODEL], "rows_truncated": len(rows) > MAX_ROWS_TO_MODEL,
            "warnings": envelope.get("warnings", []),
        }
    return {
        "success": True, "chart_id": data["chart_id"], "result_id": data["result_id"],
        "chart_type": data["chart_type"], "x": data["x"], "y": data["y"],
        "points": len(data["plot_data"]), "warnings": envelope.get("warnings", []),
    }
