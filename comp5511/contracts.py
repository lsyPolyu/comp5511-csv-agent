"""Shared strict tool arguments and the common result envelope."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Name = Annotated[str, Field(min_length=1)]
Scalar = str | int | float


class StrictContract(BaseModel):
    # Pydantic 2 strict validation and explicit extra/finite protections:
    # https://pydantic.dev/docs/validation/latest/concepts/strict_mode/
    # https://pydantic.dev/docs/validation/latest/api/pydantic/config/
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Filter(StrictContract):
    column: Name
    op: Literal["eq", "ne", "gt", "ge", "lt", "le", "in"]
    value: Scalar | list[Scalar] | None


class Metric(StrictContract):
    operation: Literal["row_count", "count", "sum", "mean"]
    column: Name | None = None
    alias: Name

    @model_validator(mode="after")
    def target_matches_operation(self):
        if not self.alias.strip():
            raise ValueError("Metric alias must not be blank.")
        if self.operation == "row_count" and self.column is not None:
            raise ValueError("row_count does not accept a target column.")
        if self.operation != "row_count" and self.column is None:
            raise ValueError("This operation requires a target column.")
        return self


class Sort(StrictContract):
    column: Name
    direction: Literal["asc", "desc"] = "asc"


class AggregateRequest(StrictContract):
    filters: list[Filter] = Field(default_factory=list)
    group_by: list[Name] = Field(default_factory=list)
    metrics: list[Metric] = Field(min_length=1)
    sort_by: list[Sort] = Field(default_factory=list)

    @model_validator(mode="after")
    def result_names_are_unique(self):
        aliases = [metric.alias for metric in self.metrics]
        if len(self.group_by) != len(set(self.group_by)):
            raise ValueError("Grouping columns must be unique.")
        if len(aliases) != len(set(aliases)) or set(aliases) & set(self.group_by):
            raise ValueError("Metric aliases must be unique and distinct from grouping columns.")
        return self


class PlotRequest(StrictContract):
    """Only fields from a registered result may supply chart values."""

    result_id: Name
    chart_type: Literal["bar", "line"]
    x: Name
    y: Name
    title: Name
    x_label: Name
    y_label: Name
    x_kind: Literal["category", "numeric", "date"] | None = None
    date_format: str | None = None
    y_format: Literal["number", "percent"] = "number"
    decimal_places: Annotated[int, Field(ge=0, le=6)] = 2
    unit: Name = "unknown"

    @model_validator(mode="after")
    def format_is_explicit(self):
        for text in (self.title, self.x_label, self.y_label):
            if not text.strip() or not text.isprintable():
                raise ValueError("Title and axis labels must be non-empty printable text.")
        if not self.unit.strip() or not self.unit.isascii() or not any(letter.isalpha() for letter in self.unit):
            raise ValueError("Unit must be non-empty English text.")
        kind = self.x_kind or ("category" if self.chart_type == "bar" else "numeric")
        if self.chart_type == "line" and kind == "category":
            raise ValueError("Line charts require a numeric or date x axis.")
        if kind == "date":
            if self.date_format != "%Y-%m-%d":
                raise ValueError("Date axes require the explicit format %Y-%m-%d.")
        elif self.date_format is not None:
            raise ValueError("date_format is only allowed for date axes.")
        if self.y_format == "percent" and (
            self.unit != "fraction" or not any(label in self.y_label for label in ("(%)", "(percent)"))
        ):
            raise ValueError("Percent display requires unit=fraction and a (%) or (percent) y label.")
        return self


def error_result(code: str, message: str, field: str | None = None,
                 error_stage: str = "dataset_validation") -> dict:
    return {
        "success": False, "data": None, "warnings": [],
        "error": {"code": code, "field": field, "message": message, "error_stage": error_stage},
    }
