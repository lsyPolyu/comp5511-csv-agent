"""Server-owned analysis context; result references never cross its boundaries."""

from copy import deepcopy
import json
from uuid import uuid4

from pydantic import ValidationError

from comp5511.contracts import AggregateRequest, error_result
from comp5511.datasets import Dataset


class AnalysisSession:
    """Own a browser session's dataset, run, results, and single chart artifact."""

    def __init__(self) -> None:
        self.session_id = str(uuid4())
        self.dataset: Dataset | None = None
        self.run_id: str | None = None
        self.current_result_id: str | None = None
        self._results: dict[str, dict] = {}
        self.current_chart_id: str | None = None
        self._chart: tuple[dict, bytes] | None = None

    def _clear_chart(self) -> None:
        self.current_chart_id = None
        self._chart = None

    def clear_dataset(self) -> None:
        """Invalidate before attempting a replacement, including failed loads."""
        self.dataset = None
        self.run_id = None
        self.current_result_id = None
        self._results.clear()
        self._clear_chart()

    def replace_dataset(self, dataset: Dataset) -> None:
        self.clear_dataset()
        self.dataset = dataset

    def begin_run(self) -> str:
        """Start only on an explicit submission; ordinary reads never call this."""
        if self.dataset is None:
            raise ValueError("Upload a valid CSV before starting an analysis run.")
        self.run_id = str(uuid4())
        self.current_result_id = None
        self._results.clear()
        self._clear_chart()
        return self.run_id

    def _matches_context(self, data: dict) -> bool:
        return (
            self.dataset is not None
            and self.run_id is not None
            and data.get("session_id") == self.session_id
            and data.get("dataset_id") == self.dataset.dataset_id
            and data.get("run_id") == self.run_id
        )

    @staticmethod
    def _invalid_reference() -> dict:
        return error_result(
            "INVALID_RESULT_REFERENCE",
            "Result is unavailable in the current session, dataset, or run.",
            "result_id",
        )

    def publish_result(self, response: dict) -> dict:
        """Register only a complete success produced for the active context."""
        if isinstance(response, dict) and response.get("success") is False:
            return deepcopy(response)
        if not self._is_complete_success(response):
            return self._invalid_reference()
        data = response["data"]
        result_id = data["result_id"]
        if not self._matches_context(data) or result_id in self._results:
            return self._invalid_reference()
        self._clear_chart()
        self._results[result_id] = deepcopy(response)
        self.current_result_id = result_id
        return deepcopy(response)

    @staticmethod
    def _is_complete_success(response: object) -> bool:
        if not isinstance(response, dict) or response.get("success") is not True:
            return False
        if "error" not in response or response["error"] is not None:
            return False
        if not isinstance(response.get("warnings"), list):
            return False
        data = response.get("data")
        if not isinstance(data, dict):
            return False
        if any(not isinstance(data.get(key), str) or not data[key] for key in (
            "result_id", "session_id", "dataset_id", "run_id"
        )):
            return False
        if type(data.get("filtered_row_count")) is not int or data["filtered_row_count"] < 0:
            return False
        try:
            request = AggregateRequest.model_validate(data.get("operations"))
            json.dumps(response, allow_nan=False)
        except (ValidationError, TypeError, ValueError):
            return False
        if data.get("group_by") != request.group_by or data.get("metrics") != [
            metric.model_dump() for metric in request.metrics
        ]:
            return False
        fields = data.get("fields")
        expected = [(name, "group") for name in request.group_by] + [
            (metric.alias, "metric") for metric in request.metrics
        ]
        if not isinstance(fields, list) or len(fields) != len(expected):
            return False
        for field, (name, role) in zip(fields, expected):
            if not isinstance(field, dict) or field.get("name") != name or field.get("role") != role:
                return False
            if field.get("logical_type") not in ("numeric", "text", "unknown"):
                return False
        names = {name for name, _ in expected}
        rows = data.get("rows")
        return isinstance(rows, list) and all(
            isinstance(row, dict) and set(row) == names for row in rows
        )

    def resolve_result(self, result_id: str) -> dict:
        """Return a detached envelope, without revealing other contexts."""
        result = self._results.get(result_id) if isinstance(result_id, str) else None
        if result is None or not self._matches_context(result["data"]):
            return self._invalid_reference()
        return deepcopy(result)

    def current_result(self) -> dict | None:
        if self.current_result_id is None:
            return None
        result = self.resolve_result(self.current_result_id)
        return result if result["success"] else None

    @staticmethod
    def _invalid_chart_reference() -> dict:
        return error_result(
            "INVALID_CHART_REFERENCE",
            "Chart is unavailable in the current session, dataset, or run.",
            "chart_id",
        )

    def publish_chart(self, response: dict, png_bytes: bytes) -> dict:
        """Keep one detached chart artifact, only for a registered source result."""
        if isinstance(response, dict) and response.get("success") is False:
            return deepcopy(response)
        if not self._is_complete_chart(response, png_bytes):
            return self._invalid_chart_reference()
        data = response["data"]
        source = self.resolve_result(data["result_id"])
        if not self._matches_context(data) or not source["success"]:
            return self._invalid_reference()
        if not self._chart_matches_source(data, source["data"]):
            return self._invalid_chart_reference()
        if data["chart_id"] == getattr(self, "current_chart_id", None):
            return self._invalid_chart_reference()
        self._chart = (deepcopy(response), png_bytes)
        self.current_chart_id = data["chart_id"]
        return deepcopy(response)

    @staticmethod
    def _is_complete_chart(response: object, png_bytes: object) -> bool:
        if not isinstance(response, dict) or response.get("success") is not True:
            return False
        if response.get("error", False) is not None or not isinstance(response.get("warnings"), list):
            return False
        data = response.get("data")
        if not isinstance(data, dict) or any(
            not isinstance(data.get(name), str) or not data[name] for name in (
                "chart_id", "result_id", "session_id", "dataset_id", "run_id",
                "chart_type", "x", "y", "title", "x_label", "y_label",
            )
        ):
            return False
        if data["chart_type"] not in ("bar", "line"):
            return False
        artifact = data.get("artifact")
        if not isinstance(artifact, dict) or artifact != {
            "format": "png", "mime_type": "image/png",
            "filename": data["chart_id"] + ".png", "size_bytes": len(png_bytes) if isinstance(png_bytes, bytes) else -1,
        }:
            return False
        if not isinstance(png_bytes, bytes) or not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return False
        try:
            json.dumps(response, allow_nan=False)
        except (TypeError, ValueError):
            return False
        formatting = data.get("format")
        if not isinstance(formatting, dict) or not {
            "x_kind", "date_format", "y_format", "decimal_places", "unit",
        } <= formatting.keys():
            return False
        rows = data.get("plot_data")
        return isinstance(rows, list) and bool(rows) and all(
            isinstance(row, dict)
            and {"source_index", "x", "y", "x_sort_key", "display_x", "display_y"} <= row.keys()
            and type(row["source_index"]) is int
            and isinstance(row["display_x"], str)
            and (row["display_y"] is None or isinstance(row["display_y"], str))
            for row in rows
        )

    @staticmethod
    def _chart_matches_source(data: dict, source: dict) -> bool:
        """Check provenance without recalculating values or plotting decisions."""
        names = {field["name"] for field in source["fields"]}
        if data["x"] not in names or data["y"] not in names:
            return False
        if "source" in data and data["source"] != {
            key: source[key] for key in ("fields", "operations", "filtered_row_count")
        }:
            return False
        rows = source["rows"]
        plot_data = data["plot_data"]
        indices = [row["source_index"] for row in plot_data]
        if len(indices) != len(rows) or set(indices) != set(range(len(rows))):
            return False
        return all(
            point["x"] == rows[point["source_index"]][data["x"]]
            and point["y"] == rows[point["source_index"]][data["y"]]
            for point in plot_data
        )

    def resolve_chart(self, chart_id: str) -> dict:
        """Resolve only the current artifact and recheck its result's ownership."""
        if getattr(self, "_chart", None) is None or chart_id != getattr(self, "current_chart_id", None):
            return self._invalid_chart_reference()
        response, _ = self._chart
        data = response["data"]
        if not self._matches_context(data) or not self.resolve_result(data["result_id"])["success"]:
            self._clear_chart()
            return self._invalid_chart_reference()
        return deepcopy(response)

    def current_chart(self) -> dict | None:
        chart = self.resolve_chart(getattr(self, "current_chart_id", None))
        return chart if chart["success"] else None

    def chart_bytes(self, chart_id: str) -> bytes | None:
        return self._chart[1] if self.resolve_chart(chart_id)["success"] else None
