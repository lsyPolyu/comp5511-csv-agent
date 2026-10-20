"""P01 local CSV acceptance checks; no network or model calls."""

import json
from pathlib import Path

import pytest

from comp5511 import datasets
from comp5511.datasets import DatasetError, inspect_dataset, load_csv


DEV_CSV = Path(__file__).resolve().parents[1] / "data" / "dev" / "eight_rows.csv"


def column(summary, name):
    return next(item for item in summary["columns"] if item["name"] == name)


def test_development_csv_has_real_expected_summary():
    content = DEV_CSV.read_bytes()
    dataset = load_csv(content, "eight_rows.csv")
    result = inspect_dataset(dataset)

    assert result["success"] is True
    assert result["error"] is None
    assert result["warnings"] == []
    summary = result["data"]
    assert summary["dataset_id"] == dataset.dataset_id
    assert summary["row_count"] == 8
    assert [item["name"] for item in summary["columns"]] == ["Sex", "Survived", "Age"]
    assert [item["logical_type"] for item in summary["columns"]] == ["text", "numeric", "numeric"]
    assert column(summary, "Age")["missing_count"] == 2
    assert column(summary, "Age")["missing_ratio"] == 0.25
    assert column(summary, "Sex")["missing_count"] == 0
    assert len(summary["preview"]) == 5
    assert summary["preview"][2] == {"Sex": "female", "Survived": 1, "Age": None}
    assert dataset.original_bytes == content
    assert dataset.raw_rows[2] == ("female", "1", "")
    # This rejects NaN/Infinity and verifies JSON null rather than the string "nan".
    encoded = json.dumps(result, allow_nan=False)
    assert '"Age": null' in encoded


def test_utf8_bom_case_insensitive_extension_and_crlf():
    dataset = load_csv(b"\xef\xbb\xbfName,Value\r\nAlice,1\r\nBob,2\r\n", "example.CSV")
    assert dataset.headers == ("Name", "Value")
    assert dataset.raw_rows == (("Alice", "1"), ("Bob", "2"))


def test_quoted_fields_and_newlines_are_not_broken_into_rows():
    dataset = load_csv(b'Name,Note\n"Doe, Jane","line one\nline two"\n', "quoted.csv")
    assert dataset.raw_rows == (("Doe, Jane", "line one\nline two"),)
    assert inspect_dataset(dataset)["data"]["row_count"] == 1


def test_valid_text_field_is_not_rejected_by_csv_library_default_field_limit():
    value = "x" * 150_000
    dataset = load_csv(f"Note\n{value}\n".encode(), "long_text.csv")
    assert dataset.raw_rows == ((value,),)


def test_empty_lines_ignored_but_missing_only_record_is_data():
    dataset = load_csv(b"A,B\n\n,\n\r\n1,2\n", "blank.csv")
    summary = inspect_dataset(dataset)["data"]
    assert summary["row_count"] == 2
    assert column(summary, "A")["missing_count"] == 1
    assert summary["preview"][0] == {"A": None, "B": None}


@pytest.mark.parametrize(
    ("content", "error_code"),
    [
        (b"", "EMPTY_DATASET"),
        (b"\n\r\n", "EMPTY_DATASET"),
        (b"A,B\n", "EMPTY_DATASET"),
        (b"A,B\n\n", "EMPTY_DATASET"),
        (b"A,B\n\xff,1\n", "CSV_PARSE_ERROR"),
        (b'A,B\n1,"unterminated\n', "CSV_PARSE_ERROR"),
        (b"A,B\n1\n", "CSV_PARSE_ERROR"),
        (b"A,B\n1,2,3\n", "CSV_PARSE_ERROR"),
        (b"A,A\n1,2\n", "INVALID_HEADER"),
        (b",B\n1,2\n", "INVALID_HEADER"),
        (b"   ,B\n1,2\n", "INVALID_HEADER"),
    ],
)
def test_invalid_csv_has_structured_english_error(content, error_code):
    with pytest.raises(DatasetError) as caught:
        load_csv(content, "invalid.csv")
    error = caught.value
    assert error.code == error_code
    assert isinstance(error.message, str) and error.message.strip()
    assert error.message.isascii()
    assert error.field is None or isinstance(error.field, str)


def test_non_csv_extension_rejected():
    with pytest.raises(DatasetError) as caught:
        load_csv(b"A\n1\n", "example.txt")
    assert caught.value.code == "UNSUPPORTED_INPUT"


def test_size_limit_rejects_without_truncating(monkeypatch):
    monkeypatch.setattr(datasets, "MAX_UPLOAD_BYTES", 5)
    with pytest.raises(DatasetError) as caught:
        load_csv(b"A\n1234\n", "large.csv")
    assert caught.value.code == "INPUT_LIMIT_EXCEEDED"


def test_row_limit_boundary(monkeypatch):
    monkeypatch.setattr(datasets, "MAX_DATA_ROWS", 2)
    assert inspect_dataset(load_csv(b"A\n1\n2\n", "limit.csv"))["data"]["row_count"] == 2
    with pytest.raises(DatasetError) as caught:
        load_csv(b"A\n1\n2\n3\n", "large.csv")
    assert caught.value.code == "INPUT_LIMIT_EXCEEDED"


def test_nonempty_literals_and_spaces_remain_text():
    dataset = load_csv(b"Value,Other\nNA,1\nN/A,2\nnull,3\n   ,4\n,5\n", "literals.csv")
    summary = inspect_dataset(dataset)["data"]
    values = column(summary, "Value")
    assert values["logical_type"] == "text"
    assert values["missing_count"] == 1
    assert values["missing_ratio"] == 0.2
    assert [row["Value"] for row in summary["preview"]] == ["NA", "N/A", "null", "   ", None]


def test_mixed_numeric_column_is_text_without_losing_dirty_value():
    dataset = load_csv(b"Value\n1\n2.5\ninvalid\n", "mixed.csv")
    assert dataset.logical_types == ("text",)
    assert inspect_dataset(dataset)["data"]["preview"] == [
        {"Value": "1"}, {"Value": "2.5"}, {"Value": "invalid"}
    ]


def test_finite_numeric_column_and_missing_have_explicit_types():
    dataset = load_csv(b"Value,Label\n-2,one\n3.5,two\n1e2,three\n,four\n", "numeric.csv")
    summary = inspect_dataset(dataset)["data"]
    assert dataset.logical_types == ("numeric", "text")
    assert [row["Value"] for row in summary["preview"]] == [-2, 3.5, 100, None]
    assert column(summary, "Value")["missing_count"] == 1
    json.dumps(summary, allow_nan=False)


@pytest.mark.parametrize("value", ["true", "False", "2026-10-15", "NaN", "inf", "-Infinity"])
def test_no_implicit_boolean_date_or_nonfinite_numeric(value):
    dataset = load_csv(f"Value\n{value}\n".encode(), "typed.csv")
    summary = inspect_dataset(dataset)["data"]
    assert dataset.logical_types == ("text",)
    assert summary["preview"] == [{"Value": value}]
    assert column(summary, "Value")["missing_count"] == 0


def test_all_missing_column_is_unknown():
    dataset = load_csv(b"Empty,Other\n,one\n,two\n", "unknown.csv")
    summary = inspect_dataset(dataset)["data"]
    empty = column(summary, "Empty")
    assert dataset.logical_types == ("unknown", "text")
    assert empty["missing_count"] == 2
    assert empty["missing_ratio"] == 1.0
    assert [row["Empty"] for row in summary["preview"]] == [None, None]
    json.dumps(summary, allow_nan=False)


def test_column_names_preserved_without_case_or_whitespace_normalization():
    dataset = load_csv(b" Age ,Age,age\n1,2,3\n", "names.csv")
    assert dataset.headers == (" Age ", "Age", "age")
    assert list(inspect_dataset(dataset)["data"]["preview"][0]) == [" Age ", "Age", "age"]


def test_summary_limits_and_category_truncation():
    content = "Category\n" + "\n".join(f"item-{index}" for index in range(12)) + "\n"
    summary = inspect_dataset(load_csv(content.encode(), "many.csv"))["data"]
    categories = column(summary, "Category")
    assert len(summary["preview"]) == 5
    assert categories["category_samples"] == [f"item-{index}" for index in range(10)]
    assert categories["truncated"] is True


def test_reloading_same_bytes_creates_new_context():
    first = load_csv(b"A\n1\n", "same.csv")
    second = load_csv(b"A\n1\n", "same.csv")
    assert first.dataset_id != second.dataset_id


def test_typed_frames_are_copies_and_raw_data_is_immutable():
    dataset = load_csv(DEV_CSV.read_bytes(), "eight_rows.csv")
    original = inspect_dataset(dataset)
    frame = dataset.to_frame()
    assert frame.loc[2, "Age"] is None
    frame.loc[0, "Age"] = -999
    frame.loc[0, "Sex"] = "changed"
    assert inspect_dataset(dataset) == original
    assert dataset.to_frame().loc[0, "Age"] == 20
    assert dataset.raw_rows[0] == ("female", "1", "20")
    with pytest.raises((AttributeError, TypeError)):
        dataset.raw_rows = ()


def test_inspect_without_current_dataset_returns_no_dataset_error():
    result = inspect_dataset(None)
    assert result["success"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "NO_DATASET"
    assert result["warnings"] == []
