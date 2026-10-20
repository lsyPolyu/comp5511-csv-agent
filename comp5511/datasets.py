"""Explicit CSV parsing and immutable, session-owned source data."""

import csv
import io
import math
import re
from dataclasses import dataclass
from uuid import uuid4

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_DATA_ROWS = 100_000
PREVIEW_ROWS = 5
CATEGORY_SAMPLE_LIMIT = 10
csv.field_size_limit(MAX_UPLOAD_BYTES)
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class DatasetError(ValueError):
    def __init__(self, code: str, message: str, field: str = "file"):
        super().__init__(message)
        self.code, self.message, self.field = code, message, field


@dataclass(frozen=True, slots=True)
class Dataset:
    dataset_id: str
    original_bytes: bytes
    headers: tuple[str, ...]
    raw_rows: tuple[tuple[str, ...], ...]
    logical_types: tuple[str, ...]
    _typed_rows: tuple[tuple[object, ...], ...]

    def to_frame(self):
        """Return a disposable typed view; mutations cannot change the source."""
        import pandas as pd

        return pd.DataFrame(self._typed_rows, columns=self.headers, dtype=object)


def _validate_quotes(text: str) -> None:
    # csv.reader(strict=True) alone accepts bare quotes in unquoted fields.
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char == "," or char in "\r\n":
                state = "start"
            else:
                raise DatasetError("CSV_PARSE_ERROR", "Unexpected text after a closing quote.")
        elif char == '"':
            if state != "start":
                raise DatasetError("CSV_PARSE_ERROR", "Quotes must enclose a complete CSV field.")
            state = "quoted"
        elif char == "," or char in "\r\n":
            state = "start"
        else:
            state = "unquoted"
    if state == "quoted":
        raise DatasetError("CSV_PARSE_ERROR", "A quoted CSV field is not closed.")


def _typed_column(values: tuple[str, ...]) -> tuple[str, tuple[object, ...]]:
    if all(value == "" for value in values):
        return "unknown", (None,) * len(values)
    parsed = []
    for value in values:
        if value == "":
            parsed.append(None)
        elif _NUMBER.fullmatch(value.strip()):
            number = float(value)
            if not math.isfinite(number):
                break
            parsed.append(number)
        else:
            break
    else:
        return "numeric", tuple(parsed)
    return "text", tuple(None if value == "" else value for value in values)


def load_csv(content: bytes, filename: str) -> Dataset:
    """Validate the complete input before publishing a fresh dataset context."""
    if not filename.lower().endswith(".csv"):
        raise DatasetError("UNSUPPORTED_INPUT", "Upload a comma-separated .csv file.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise DatasetError("INPUT_LIMIT_EXCEEDED", "CSV exceeds the 20 MiB file limit.")
    if not content:
        raise DatasetError("EMPTY_DATASET", "CSV is empty. Include a header and data rows.")
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise DatasetError("CSV_PARSE_ERROR", "CSV must use UTF-8 or UTF-8-BOM encoding.") from None
    if not text.strip():
        raise DatasetError("EMPTY_DATASET", "CSV contains no header or data rows.")
    if "\x00" in text:
        raise DatasetError("CSV_PARSE_ERROR", "CSV contains an unsupported null byte.")
    _validate_quotes(text)
    headers = None
    rows = []
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        for row in reader:
            if not row:
                continue
            if headers is None:
                if any(not name.strip() for name in row) or len(set(row)) != len(row):
                    raise DatasetError("INVALID_HEADER", "Column names must be nonempty and unique.", "header")
                headers = tuple(row)
            else:
                if len(row) != len(headers):
                    raise DatasetError("CSV_PARSE_ERROR", f"CSV row ending at line {reader.line_num} has the wrong number of fields.")
                rows.append(tuple(row))
                if len(rows) > MAX_DATA_ROWS:
                    raise DatasetError("INPUT_LIMIT_EXCEEDED", "CSV exceeds the 100,000 data row limit.")
    except csv.Error:
        raise DatasetError("CSV_PARSE_ERROR", f"CSV could not be parsed at line {reader.line_num}.") from None
    if not rows:
        raise DatasetError("EMPTY_DATASET", "CSV has no data rows. A header alone is not a dataset.")
    types_and_columns = tuple(_typed_column(column) for column in zip(*rows))
    return Dataset(
        dataset_id=str(uuid4()),
        original_bytes=content,
        headers=headers,
        raw_rows=tuple(rows),
        logical_types=tuple(item[0] for item in types_and_columns),
        _typed_rows=tuple(zip(*(item[1] for item in types_and_columns))),
    )


def inspect_dataset(dataset: Dataset | None) -> dict:
    """Inspect only the dataset supplied by the current server-side session."""
    if dataset is None:
        return {
            "success": False, "data": None, "warnings": [],
            "error": {"code": "NO_DATASET", "field": "dataset", "message": "Upload a valid CSV first.", "error_stage": "execution"},
        }
    row_count = len(dataset.raw_rows)
    columns = []
    for index, (name, logical_type) in enumerate(zip(dataset.headers, dataset.logical_types)):
        missing_count = sum(row[index] == "" for row in dataset.raw_rows)
        samples = []
        truncated = False
        if logical_type == "text":
            for row in dataset.raw_rows:
                value = row[index]
                if value != "" and value not in samples:
                    if len(samples) == CATEGORY_SAMPLE_LIMIT:
                        truncated = True
                        break
                    samples.append(value)
        columns.append({
            "name": name, "logical_type": logical_type,
            "missing_count": missing_count, "missing_ratio": missing_count / row_count,
            "category_samples": samples, "truncated": truncated,
        })
    return {
        "success": True, "error": None, "warnings": [],
        "data": {
            "dataset_id": dataset.dataset_id, "row_count": row_count, "columns": columns,
            "preview": [dict(zip(dataset.headers, row)) for row in dataset._typed_rows[:PREVIEW_ROWS]],
        },
    }
