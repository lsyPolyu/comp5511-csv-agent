"""P02 local statistics, with expected values from specification and hand calculation."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from comp5511.analysis import aggregate_data
from comp5511.datasets import load_csv

DEV_CSV = Path(__file__).resolve().parents[1] / "data" / "dev" / "eight_rows.csv"


@pytest.fixture
def sample():
    return load_csv(DEV_CSV.read_bytes(), "eight_rows.csv")


def run(dataset, metrics, **kwargs):
    return aggregate_data(dataset, {"metrics": metrics, **kwargs}, session_id="session-a", run_id="run-a")


def test_hand_calculated_eight_row_metrics_and_metadata(sample):
    original = (sample.original_bytes, sample.raw_rows, sample._typed_rows)
    metrics = [
        {"operation": "row_count", "alias": "Rows"},
        {"operation": "count", "column": "Age", "alias": "Known ages"},
        {"operation": "sum", "column": "Age", "alias": "Total age"},
        {"operation": "mean", "column": "Age", "alias": "Mean age"},
    ]
    result = run(sample, metrics)
    assert result["success"] is True
    assert result["error"] is None
    assert result["warnings"] == []
    data = result["data"]
    assert data["rows"] == [{"Rows": 8, "Known ages": 6, "Total age": 160, "Mean age": pytest.approx(80 / 3)}]
    assert data["session_id"] == "session-a" and data["run_id"] == "run-a"
    assert data["dataset_id"] == sample.dataset_id
    assert data["filtered_row_count"] == 8
    assert UUID(data["result_id"])
    assert data["fields"] == [{"name": metric["alias"], "logical_type": "numeric", "role": "metric"} for metric in metrics]
    assert data["operations"]["metrics"] == data["metrics"]
    assert (sample.original_bytes, sample.raw_rows, sample._typed_rows) == original
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("arguments", [
    {}, {"metrics": []}, {"metrics": [{"operation": "count", "alias": "Count"}]},
    {"metrics": [{"operation": "row_count", "column": "Age", "alias": "Rows"}]},
    {"metrics": [{"operation": "median", "column": "Age", "alias": "Median"}]},
    {"metrics": [{"operation": "row_count", "alias": " "}]},
    {"metrics": [{"operation": "row_count", "alias": "Rows", "extra": 1}]},
    {"metrics": [{"operation": "row_count", "alias": "Rows"}], "extra": True},
])
def test_invalid_schema_has_structured_error(sample, arguments):
    result = aggregate_data(sample, arguments, session_id="s", run_id="r")
    assert result["success"] is False and result["data"] is None
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    assert result["error"]["error_stage"] == "schema"


def test_missing_dataset_and_illegal_numeric_aggregation(sample):
    assert run(None, [{"operation": "row_count", "alias": "Rows"}])["error"]["code"] == "NO_DATASET"
    assert run(sample, [{"operation": "mean", "column": "Sex", "alias": "Mean"}])["error"]["code"] == "INCOMPATIBLE_AGGREGATION"
    assert run(sample, [{"operation": "count", "column": "age", "alias": "Count"}])["error"]["code"] == "INVALID_COLUMN"


def test_numeric_overflow_fails_without_a_partial_result():
    dataset = load_csv(b"Value\n1e308\n1e308\n", "large.csv")
    result = run(dataset, [{"operation": "sum", "column": "Value", "alias": "Total"}])
    assert result["success"] is False and result["data"] is None
    assert result["error"]["code"] == "NUMERIC_ERROR"
    assert result["error"]["error_stage"] == "execution"
    # A finite mean should remain valid even when an intermediate raw sum overflows.
    assert run(dataset, [{"operation": "mean", "column": "Value", "alias": "Mean"}])["data"]["rows"] == [{"Mean": 1e308}]


def test_mean_preserves_representable_subnormal_values():
    dataset = load_csv(b"Value\n5e-324\n5e-324\n", "tiny.csv")
    assert run(dataset, [{"operation": "mean", "column": "Value", "alias": "Mean"}])["data"]["rows"] == [{"Mean": 5e-324}]


@pytest.mark.parametrize(("op", "value", "expected"), [
    ("eq", 20, 2), ("ne", 20, 4), ("gt", 30, 2), ("ge", 30, 3),
    ("lt", 20, 1), ("le", 20, 3), ("in", [10, 40], 3), ("in", [], 0),
])
def test_numeric_operators_exclude_missing_values(sample, op, value, expected):
    result = run(sample, [{"operation": "row_count", "alias": "Rows"}],
                 filters=[{"column": "Age", "op": op, "value": value}])
    assert result["success"] is True
    assert result["data"]["rows"] == [{"Rows": expected}]
    assert result["data"]["filtered_row_count"] == expected


def test_filters_use_and_and_legal_empty_result_is_not_repaired(sample):
    metrics = [{"operation": "row_count", "alias": "Rows"},
               {"operation": "count", "column": "Age", "alias": "Count"},
               {"operation": "sum", "column": "Age", "alias": "Sum"},
               {"operation": "mean", "column": "Age", "alias": "Mean"}]
    selected = run(sample, metrics, filters=[{"column": "Age", "op": "ge", "value": 30},
                                            {"column": "Sex", "op": "eq", "value": "female"}])
    assert selected["data"]["rows"] == [{"Rows": 2, "Count": 2, "Sum": 70, "Mean": 35}]
    filters = [{"column": "Age", "op": "gt", "value": 100}]
    empty = run(sample, metrics, filters=filters)
    assert empty["success"] is True
    assert empty["data"]["rows"] == [{"Rows": 0, "Count": 0, "Sum": None, "Mean": None}]
    assert empty["data"]["operations"]["filters"] == filters
    assert {warning["code"] for warning in empty["warnings"]} == {"EMPTY_RESULT", "NO_VALID_VALUES"}
    assert len(empty["data"]["fields"]) == 4
    missing_category = run(sample, metrics, filters=[{"column": "Sex", "op": "eq", "value": "unlisted"}])
    assert missing_category["success"] is True
    assert missing_category["data"]["filtered_row_count"] == 0
    assert missing_category["warnings"][0]["code"] == "EMPTY_RESULT"
    json.dumps(empty, allow_nan=False)


@pytest.mark.parametrize(("column", "op", "value"), [
    ("Age", "eq", "20"), ("Sex", "eq", 1), ("Sex", "gt", "female"),
    ("Age", "in", [10, "20"]), ("Age", "in", 20), ("Sex", "eq", ["male"]),
    ("Age", "eq", None), ("Sex", "ne", None),
])
def test_no_implicit_filter_type_conversion(sample, column, op, value):
    result = run(sample, [{"operation": "row_count", "alias": "Rows"}],
                 filters=[{"column": column, "op": op, "value": value}])
    assert result["success"] is False and result["data"] is None
    assert result["error"]["code"] == "INVALID_FILTER_TYPE"
    assert result["error"]["error_stage"] == "dataset_validation"


@pytest.mark.parametrize("value", [True, False, float("inf"), float("nan"), [True], [float("inf")], {}])
def test_strict_filter_schema_rejects_boolean_nonfinite_and_objects(sample, value):
    result = run(sample, [{"operation": "row_count", "alias": "Rows"}],
                 filters=[{"column": "Age", "op": "eq", "value": value}])
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    assert result["error"]["error_stage"] == "schema"


def test_literal_na_and_numeric_text_have_exact_text_filter_semantics():
    dataset = load_csv(b"Value\nNA\nN/A\nnull\n1\n\"\"\n", "literals.csv")
    for value in ("NA", "N/A", "null", "1"):
        assert run(dataset, [{"operation": "row_count", "alias": "Rows"}],
                   filters=[{"column": "Value", "op": "eq", "value": value}])["data"]["rows"] == [{"Rows": 1}]
    result = run(dataset, [{"operation": "row_count", "alias": "Rows"}],
                 filters=[{"column": "Value", "op": "ne", "value": "NA"}])
    assert result["data"]["rows"] == [{"Rows": 3}]


def test_grouped_survival_mean_and_filtered_group_means(sample):
    metrics = [{"operation": "mean", "column": "Survived", "alias": "Survival rate"}]
    result = run(sample, metrics, group_by=["Sex"])
    assert result["data"]["rows"] == [{"Sex": "female", "Survival rate": 0.75}, {"Sex": "male", "Survival rate": 0.25}]
    assert result["data"]["fields"][0] == {"name": "Sex", "logical_type": "text", "role": "group"}
    filtered = run(sample, metrics, group_by=["Sex"], filters=[{"column": "Age", "op": "ge", "value": 30}])
    assert filtered["data"]["filtered_row_count"] == 3
    assert filtered["data"]["rows"] == [{"Sex": "female", "Survival rate": 0.5}, {"Sex": "male", "Survival rate": 0.0}]
    empty = run(sample, metrics, group_by=["Sex"], filters=[{"column": "Age", "op": "gt", "value": 100}])
    assert empty["success"] is True and empty["data"]["rows"] == []
    assert empty["data"]["filtered_row_count"] == 0
    assert empty["data"]["fields"] == result["data"]["fields"]
    assert [warning["code"] for warning in empty["warnings"]] == ["EMPTY_RESULT"]


def test_null_group_is_retained_and_distinct_from_literal_label(sample):
    content = sample.original_bytes.replace(b"\nmale,0,40", b"\n,0,40")
    dataset = load_csv(content, "null_group.csv")
    result = run(dataset, [{"operation": "row_count", "alias": "Rows"}], group_by=["Sex"])
    assert result["data"]["rows"] == [{"Sex": "female", "Rows": 4}, {"Sex": "male", "Rows": 3}, {"Sex": None, "Rows": 1}]
    literal = load_csv(b"Group,Value\n,1\n(missing),2\n", "labels.csv")
    assert run(literal, [{"operation": "row_count", "alias": "Rows"}], group_by=["Group"])["data"]["rows"] == [
        {"Group": "(missing)", "Rows": 1}, {"Group": None, "Rows": 1}]
    json.dumps(result, allow_nan=False)


def test_known_numeric_all_missing_group_and_unknown_whole_column():
    dataset = load_csv(b"Group,Age\nfemale,\nfemale,\nmale,10\nmale,20\n", "missing_group.csv")
    metrics = [{"operation": "count", "column": "Age", "alias": "Count"},
               {"operation": "sum", "column": "Age", "alias": "Sum"},
               {"operation": "mean", "column": "Age", "alias": "Mean"}]
    result = run(dataset, metrics, group_by=["Group"])
    assert result["data"]["rows"] == [
        {"Group": "female", "Count": 0, "Sum": None, "Mean": None},
        {"Group": "male", "Count": 2, "Sum": 30, "Mean": 15}]
    assert [warning["code"] for warning in result["warnings"]] == ["NO_VALID_VALUES", "NO_VALID_VALUES"]
    unknown = load_csv(b"Group,Age\nfemale,\nmale,\n", "unknown.csv")
    assert run(unknown, metrics[:1])["data"]["rows"] == [{"Count": 0}]
    for metric in metrics[1:]:
        failure = run(unknown, [metric])
        assert failure["error"]["code"] == "INCOMPATIBLE_AGGREGATION"
    assert run(unknown, metrics[:1], filters=[{"column": "Age", "op": "eq", "value": 1}])["error"]["code"] == "INVALID_FILTER_TYPE"


@pytest.mark.parametrize("direction,expected", [("asc", ["a", "b", None]), ("desc", ["b", "a", None])])
def test_nulls_are_last_for_both_sort_directions(direction, expected):
    dataset = load_csv(b"Group,Value\nb,2\n,3\na,1\n", "sort.csv")
    result = run(dataset, [{"operation": "sum", "column": "Value", "alias": "Total"}],
                 group_by=["Group"], sort_by=[{"column": "Group", "direction": direction}])
    assert [row["Group"] for row in result["data"]["rows"]] == expected


def test_multi_key_sort_precedence_ties_stable_and_metric_null_last():
    dataset = load_csv(b"Group,Category,Value\nb,x,2\na,x,2\nc,y,1\nd,y,1\ne,y,\n", "sort.csv")
    metrics = [{"operation": "sum", "column": "Value", "alias": "Total"}]
    grouped = ["Group", "Category"]
    # Equal Category/Total leaves b before a and c before d in source group order.
    result = run(dataset, metrics, group_by=grouped,
                 sort_by=[{"column": "Category", "direction": "desc"}, {"column": "Total", "direction": "desc"}])
    assert [row["Group"] for row in result["data"]["rows"]] == ["c", "d", "e", "b", "a"]
    default = run(dataset, metrics, group_by=grouped)
    assert [row["Group"] for row in default["data"]["rows"]] == ["a", "b", "c", "d", "e"]
    for direction in ("asc", "desc"):
        result = run(dataset, metrics, group_by=grouped, sort_by=[{"column": "Total", "direction": direction}])
        assert result["data"]["rows"][-1]["Group"] == "e"


@pytest.mark.parametrize("overrides,code,stage", [
    ({"group_by": ["sex"]}, "INVALID_COLUMN", "dataset_validation"),
    ({"group_by": ["Sex", "Sex"]}, "INVALID_ARGUMENTS", "schema"),
    ({"filters": [{"column": "age", "op": "eq", "value": 20}]}, "INVALID_COLUMN", "dataset_validation"),
    ({"sort_by": [{"column": "Age"}]}, "INVALID_SORT_FIELD", "dataset_validation"),
    ({"sort_by": [{"column": "Rows", "direction": "descending"}]}, "INVALID_ARGUMENTS", "schema"),
])
def test_invalid_group_filter_or_sort_does_not_create_result(sample, overrides, code, stage):
    result = run(sample, [{"operation": "row_count", "alias": "Rows"}], **overrides)
    assert result["success"] is False and result["data"] is None
    assert result["error"]["code"] == code
    assert result["error"]["error_stage"] == stage


def test_alias_collisions_are_rejected_and_original_names_can_be_metric_aliases(sample):
    duplicate = [{"operation": "row_count", "alias": "Same"}, {"operation": "count", "column": "Age", "alias": "Same"}]
    assert run(sample, duplicate)["error"]["code"] == "INVALID_ARGUMENTS"
    assert run(sample, [{"operation": "row_count", "alias": "Sex"}], group_by=["Sex"])["error"]["code"] == "INVALID_ARGUMENTS"
    assert run(sample, [{"operation": "mean", "column": "Age", "alias": "Age"}])["data"]["rows"] == [{"Age": pytest.approx(80 / 3)}]


def test_model_instance_is_revalidated_and_successful_calls_have_distinct_ids(sample):
    from comp5511.contracts import AggregateRequest

    request = AggregateRequest(metrics=[{"operation": "row_count", "alias": "Rows"}])
    first = aggregate_data(sample, request, session_id="s", run_id="r")
    second = aggregate_data(sample, request, session_id="s", run_id="r")
    assert first["data"]["rows"] == second["data"]["rows"]
    assert first["data"]["result_id"] != second["data"]["result_id"]
    request.metrics.clear()
    assert aggregate_data(sample, request, session_id="s", run_id="r")["error"]["code"] == "INVALID_ARGUMENTS"
