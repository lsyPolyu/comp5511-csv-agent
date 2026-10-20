"""Objective scoring of one agent run against an independent reference.

A run succeeds only if
1. its status is "completed";
2. a result table produced in the run (those cited in the answer, if any are
   cited, otherwise all of them) has the same grouping columns, the same group
   keys and, in one metric column, values within tolerance of the reference;
3. chart tasks: a chart of the requested type was drawn from a matching result,
   with x = a grouping column, y = the matching metric and non-empty labels;
4. comparison tasks: the answer names the winning group before any losing group.
Successful tool execution alone is never counted as success.
"""

from __future__ import annotations

import json
import math
import re

ABS_TOL = 1e-6
REL_TOL = 1e-9


def _key(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return str(value)


def close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return abs(a - b) <= max(ABS_TOL, REL_TOL * abs(b))


def matching_metric(result: dict, ref: dict) -> str | None:
    """Return the alias of a metric column that reproduces the reference, else None."""
    group_by = result.get("group_by", [])
    if sorted(group_by) != sorted(ref["group_by"]):
        return None
    metrics = [field["name"] for field in result.get("fields", []) if field.get("role") == "metric"]
    expected = ref["rows"]
    rows = result.get("rows", [])
    if len(rows) != len(expected):
        return None
    for alias in metrics:
        got = {}
        for row in rows:
            key = json.dumps([_key(row.get(name)) for name in ref["group_by"]])
            got[key] = row.get(alias)
        if set(got) == set(expected) and all(close(got[key], expected[key]) for key in expected):
            return alias
    return None


def _first(pattern: str, text: str) -> int | None:
    found = re.search(pattern, text, flags=re.IGNORECASE)
    return found.start() if found else None


def score_run(task: dict, ref: dict, record: dict) -> dict:
    """record: {"status", "answer", "results": {result_id: {...}}, "chart": {...} | None}."""
    if record.get("status") != "completed":
        return {"success": False, "reason": f"status:{record.get('status')}"}
    results = record.get("results") or {}
    answer = record.get("answer") or ""
    cited = [result_id for result_id in results if result_id in answer]
    candidates = cited or list(results)
    matched = {result_id: matching_metric(results[result_id], ref) for result_id in candidates}
    matched = {result_id: alias for result_id, alias in matched.items() if alias}
    if not matched:
        return {"success": False, "reason": "no_matching_table" if results else "no_table"}
    if task.get("chart"):
        chart = record.get("chart")
        if not chart:
            return {"success": False, "reason": "no_chart"}
        if chart.get("chart_type") != task["chart"]:
            return {"success": False, "reason": "wrong_chart_type"}
        source = results.get(chart.get("result_id"))
        alias = matching_metric(source, ref) if source else None
        if not alias:
            return {"success": False, "reason": "chart_from_wrong_result"}
        if chart.get("x") not in ref["group_by"] or chart.get("y") != alias:
            return {"success": False, "reason": "chart_wrong_axes"}
        if not all(str(chart.get(name) or "").strip() for name in ("title", "x_label", "y_label")):
            return {"success": False, "reason": "chart_missing_labels"}
    check = task.get("answer_check")
    if check:
        winner, loser = _first(check["winner_pattern"], answer), _first(check["loser_pattern"], answer)
        if winner is None or (loser is not None and loser < winner):
            return {"success": False, "reason": "answer_wrong_winner"}
    return {"success": True, "reason": "ok"}


def snapshot(session, run) -> dict:
    """Collect what scoring needs from a finished run (stored in the JSONL log)."""
    results = {}
    for result_id in run.result_ids:
        resolved = session.resolve_result(result_id)
        if resolved["success"]:
            data = resolved["data"]
            results[result_id] = {"group_by": data["group_by"], "fields": data["fields"], "rows": data["rows"],
                                  "operations": data["operations"]}
    chart = None
    if run.chart_id:
        resolved = session.resolve_chart(run.chart_id)
        if resolved["success"]:
            data = resolved["data"]
            chart = {key: data[key] for key in ("chart_id", "result_id", "chart_type", "x", "y",
                                                  "title", "x_label", "y_label")}
    return {"results": results, "chart": chart}
