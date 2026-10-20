"""Deterministic fault injection: replace one field in the model's FIRST call of
the target tool, identically for every mode. Injection happens before validation
and execution, adds no model request, and is recorded (before/after values)."""

from __future__ import annotations

import json
from pathlib import Path

FAULTS_FILE = Path(__file__).with_name("faults.json")


def load_faults() -> list[dict]:
    return json.loads(FAULTS_FILE.read_text(encoding="utf-8"))


class Injector:
    def __init__(self, fault: dict):
        self.fault = fault
        self.triggered = None  # the record of the injection, once it happened
        self.seen_target = False

    def __call__(self, name: str, raw_arguments: str):
        if self.seen_target or name != self.fault["tool"]:
            return raw_arguments, None
        self.seen_target = True  # only the first call of the target tool is eligible
        try:
            args = json.loads(raw_arguments)
        except (TypeError, json.JSONDecodeError):
            return raw_arguments, None
        record = self._apply(args)
        if record is None:
            return raw_arguments, None
        self.triggered = {"fault_id": self.fault["fault_id"], **record}
        return json.dumps(args), self.triggered

    def _apply(self, args: dict):
        fault, op, value = self.fault, self.fault["op"], self.fault["value"]
        if op == "set_group_by":
            items = args.get("group_by") or []
            if len(items) > fault["index"]:
                before, items[fault["index"]] = items[fault["index"]], value
                return {"field": f"group_by.{fault['index']}", "before": before, "after": value}
        elif op == "set_metric_column":
            metrics = args.get("metrics") or []
            if len(metrics) > fault["index"] and isinstance(metrics[fault["index"]], dict) \
                    and metrics[fault["index"]].get("column"):
                before = metrics[fault["index"]]["column"]
                metrics[fault["index"]]["column"] = value
                return {"field": f"metrics.{fault['index']}.column", "before": before, "after": value}
        elif op in ("set_filter_value", "set_filter_column"):
            for index, condition in enumerate(args.get("filters") or []):
                if isinstance(condition, dict) and condition.get("column") == fault["column"]:
                    key = "value" if op == "set_filter_value" else "column"
                    before, condition[key] = condition.get(key), value
                    return {"field": f"filters.{index}.{key}", "before": before, "after": value}
        elif op == "set_field":
            if fault["field"] in args:
                before, args[fault["field"]] = args[fault["field"]], value
                return {"field": fault["field"], "before": before, "after": value}
        return None
