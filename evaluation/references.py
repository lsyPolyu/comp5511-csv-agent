"""Independent reference answers computed directly with Pandas.

This module must NOT import anything from comp5511 (the agent's tools), so a
bug in the agent's statistics cannot also produce the "correct" answer.
Rules match the documented data rules: only empty fields are missing; filters
never match a missing value (including 'ne'); groups keep missing keys;
count = non-missing values; sum/mean skip missing values.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = {"titanic": ROOT / "data" / "raw" / "train.csv", "bike": ROOT / "data" / "raw" / "day.csv"}
TASKS_FILE = Path(__file__).with_name("tasks.json")


def load_frame(dataset: str) -> pd.DataFrame:
    # Only empty fields are missing; text such as "NA" stays text.
    return pd.read_csv(DATA_FILES[dataset], keep_default_na=False, na_values=[""])


def load_tasks(split: str | None = None) -> list[dict]:
    tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    return [task for task in tasks if split is None or task["split"] == split]


def _mask(frame: pd.DataFrame, condition: dict) -> pd.Series:
    column, op, value = frame[condition["column"]], condition["op"], condition["value"]
    present = column.notna()
    if op == "in":
        return present & column.isin(value)
    compare = {"eq": column.eq, "ne": column.ne, "gt": column.gt, "ge": column.ge,
               "lt": column.lt, "le": column.le}[op]
    return present & compare(value)


def _metric(series_or_frame, operation: str):
    if operation == "row_count":
        return len(series_or_frame)
    if operation == "count":
        return int(series_or_frame.count())
    valid = series_or_frame.dropna()
    if valid.empty:
        return None
    return float(valid.sum()) if operation == "sum" else float(valid.mean())


def _key(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return str(value)


def reference(task: dict, frame: pd.DataFrame | None = None) -> dict:
    """Return {"group_by": [...], "rows": {key_tuple_as_json: value}}."""
    spec = task["spec"]
    frame = load_frame(task["dataset"]) if frame is None else frame
    for condition in spec["filters"]:
        frame = frame[_mask(frame, condition)]
    operation, column = spec["metric"]["operation"], spec["metric"]["column"]
    rows = {}
    if spec["group_by"]:
        for key, group in frame.groupby(spec["group_by"], dropna=False, sort=True):
            key = key if isinstance(key, tuple) else (key,)
            target = group if operation == "row_count" else group[column]
            rows[json.dumps([_key(part) for part in key])] = _metric(target, operation)
    else:
        target = frame if operation == "row_count" else frame[column]
        rows["[]"] = _metric(target, operation)
    return {"group_by": list(spec["group_by"]), "rows": rows}


def all_references(split: str | None = None) -> dict:
    frames = {name: load_frame(name) for name in DATA_FILES}
    return {task["task_id"]: reference(task, frames[task["dataset"]]) for task in load_tasks(split)}


if __name__ == "__main__":
    for task_id, ref in all_references().items():
        print(task_id, ref["group_by"], ref["rows"])
