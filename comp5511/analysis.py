"""Local statistics over an immutable Dataset; no model or network access."""

import math
import operator
from uuid import uuid4

from pydantic import ValidationError

from comp5511.contracts import AggregateRequest, Sort, error_result
from comp5511.datasets import Dataset

_COMPARE = {
    "eq": operator.eq, "ne": operator.ne, "gt": operator.gt,
    "ge": operator.ge, "lt": operator.lt, "le": operator.le,
}


def _filter_error(request, columns):
    for index, condition in enumerate(request.filters):
        field = f"filters.{index}"
        if condition.column not in columns:
            return error_result("INVALID_COLUMN", "The requested column does not exist.", f"{field}.column")
        logical_type = columns[condition.column]
        if condition.op == "in":
            values = condition.value if isinstance(condition.value, list) else None
        else:
            values = [condition.value] if not isinstance(condition.value, list) else None
        compatible = values is not None and logical_type != "unknown"
        if compatible:
            expected_types = (int, float) if logical_type == "numeric" else (str,)
            compatible = all(type(value) in expected_types for value in values)
        if condition.op in ("gt", "ge", "lt", "le") and logical_type != "numeric":
            compatible = False
        if not compatible:
            return error_result("INVALID_FILTER_TYPE", "Filter values and operator must match the column's logical type.", f"{field}.value")
    return None


def _matches(row, filters):
    for position, condition in filters:
        value = row[position]
        # Missing fields never match a comparison, including ne.
        if value is None:
            return False
        if condition.op == "in":
            if value not in condition.value:
                return False
        elif not _COMPARE[condition.op](value, condition.value):
            return False
    return True


def _aggregate_group(rows, metrics, positions, no_values):
    values = {}
    for metric in metrics:
        if metric.operation == "row_count":
            value = len(rows)
        else:
            valid = [row[positions[metric.column]] for row in rows if row[positions[metric.column]] is not None]
            if metric.operation == "count":
                value = len(valid)
            elif not valid:
                value = None
                no_values.add(metric.alias)
            elif metric.operation == "sum":
                value = math.fsum(valid)
            else:
                try:
                    value = math.fsum(valid) / len(valid)
                except OverflowError:
                    # Scale only when necessary: always scaling would underflow
                    # subnormal values even when their mean is representable.
                    value = math.fsum(number / len(valid) for number in valid)
            if isinstance(value, float) and not math.isfinite(value):
                raise OverflowError
        values[metric.alias] = value
    return values


def _sort_rows(rows, sort_by):
    # Repeated stable sorts apply the last key first. Partitioning before each
    # sort keeps null last for either direction without mixing text and numbers.
    for criterion in reversed(sort_by):
        present = [row for row in rows if row[criterion.column] is not None]
        missing = [row for row in rows if row[criterion.column] is None]
        present.sort(key=lambda row: row[criterion.column], reverse=criterion.direction == "desc")
        rows = present + missing
    return rows


def aggregate_data(dataset: Dataset | None, arguments: dict | AggregateRequest,
                   *, session_id: str, run_id: str) -> dict:
    """Validate one structured request and publish only a complete result."""
    try:
        # Revalidate model instances too: mutable lists must not bypass validation.
        values = arguments.model_dump() if isinstance(arguments, AggregateRequest) else arguments
        request = AggregateRequest.model_validate(values)
    except ValidationError as exc:
        first = exc.errors(include_input=False)[0]
        field = ".".join(str(part) for part in first["loc"]) or "arguments"
        return error_result("INVALID_ARGUMENTS", first["msg"], field, "schema")
    if dataset is None:
        return error_result("NO_DATASET", "Upload a valid CSV first.", "dataset", "execution")

    columns = dict(zip(dataset.headers, dataset.logical_types))
    positions = {name: index for index, name in enumerate(dataset.headers)}
    for index, name in enumerate(request.group_by):
        if name not in columns:
            return error_result("INVALID_COLUMN", "The requested grouping column does not exist.", f"group_by.{index}")
    for index, metric in enumerate(request.metrics):
        if metric.column is not None and metric.column not in columns:
            return error_result("INVALID_COLUMN", "The requested column does not exist.", f"metrics.{index}.column")
        if metric.operation in ("sum", "mean") and columns[metric.column] != "numeric":
            return error_result("INCOMPATIBLE_AGGREGATION", "sum and mean require a known numeric column.", f"metrics.{index}.column")
    filter_error = _filter_error(request, columns)
    if filter_error:
        return filter_error
    fields = [{"name": name, "logical_type": columns[name], "role": "group"} for name in request.group_by]
    fields.extend({"name": metric.alias, "logical_type": "numeric", "role": "metric"} for metric in request.metrics)
    for index, criterion in enumerate(request.sort_by):
        if criterion.column not in {field["name"] for field in fields}:
            return error_result("INVALID_SORT_FIELD", "Sort columns must name a result field.", f"sort_by.{index}.column")

    filters = [(positions[condition.column], condition) for condition in request.filters]
    rows = [row for row in dataset._typed_rows if _matches(row, filters)]
    warnings = [] if rows else [{"code": "EMPTY_RESULT", "message": "No rows match the filters. The filters were not changed."}]
    groups = {} if request.group_by else {(): rows}
    if request.group_by:
        for row in rows:
            key = tuple(row[positions[name]] for name in request.group_by)
            groups.setdefault(key, []).append(row)
    result_rows = []
    no_values = set()
    try:
        for key, group in groups.items():
            values = dict(zip(request.group_by, key))
            values.update(_aggregate_group(group, request.metrics, positions, no_values))
            result_rows.append(values)
    except (OverflowError, ValueError):
        return error_result("NUMERIC_ERROR", "The calculation could not produce a finite number.", "metrics", "execution")
    for metric in request.metrics:
        if metric.alias in no_values:
            warnings.append({"code": "NO_VALID_VALUES", "message": f"Metric '{metric.alias}' has no non-missing values in one or more result groups."})
    sort_by = request.sort_by or [Sort(column=name) for name in request.group_by]
    result_rows = _sort_rows(result_rows, sort_by)
    return {
        "success": True, "error": None, "warnings": warnings,
        "data": {
            "result_id": str(uuid4()), "session_id": session_id, "dataset_id": dataset.dataset_id,
            "run_id": run_id, "filtered_row_count": len(rows), "group_by": request.group_by.copy(),
            "metrics": [metric.model_dump() for metric in request.metrics],
            "fields": fields, "rows": result_rows, "operations": request.model_dump(),
        },
    }
