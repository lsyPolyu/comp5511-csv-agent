"""Render charts from registered local statistics, never from caller values."""

from datetime import date
from decimal import Decimal
from io import BytesIO
import math
import re
from threading import RLock
from uuid import uuid4

from matplotlib import font_manager, rc_context
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ft2font import FT2Font
from matplotlib.ticker import FixedLocator, FuncFormatter
from pydantic import ValidationError

from comp5511.contracts import PlotRequest, error_result

_RENDER_LOCK = RLock()


def _font_config(texts):
    """Use installed glyph-checked fonts, scoped to this one chart render."""
    required = {ord(character) for text in texts for character in text if ord(character) > 127}
    if not required:
        return {}
    # Keep existing Latin styling. Select a CJK fallback only when DejaVu Sans
    # does not cover literal titles, axes or CSV categories in this chart.
    latin_path = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans"))
    required.difference_update(FT2Font(latin_path).get_charmap())
    if not required:
        return {}
    for family in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Zen Hei"):
        try:
            path = font_manager.findfont(font_manager.FontProperties(family=family), fallback_to_default=False)
        except ValueError:
            continue
        # FT2Font.get_charmap() maps real Unicode code points to glyph indices;
        # a font name alone does not establish coverage of the actual labels.
        if required.issubset(FT2Font(path).get_charmap()):
            return {"font.family": ["DejaVu Sans", family]}
    raise ValueError("No installed chart font covers the requested labels.")


def _display_y(value, request):
    if value is None:
        return None
    suffix = "%" if request.y_format == "percent" else ""
    # Decimal avoids overflow in a display-only multiplication of a finite y.
    displayed = Decimal(str(value)) * 100 if suffix else value
    return f"{displayed:.{request.decimal_places}f}{suffix}"


def _x_points(rows, request):
    kind = request.x_kind or ("category" if request.chart_type == "bar" else "numeric")
    labels = {str(row[request.x]) for row in rows if row[request.x] is not None}
    missing_label = "(missing)"
    while missing_label in labels:
        missing_label = f"{missing_label} [null]"
    points = []
    for index, row in enumerate(rows):
        value = row[request.x]
        key = value
        if kind == "numeric":
            if type(value) not in (int, float) or not math.isfinite(value):
                return None, error_result("INVALID_PLOT_X", "Numeric x values must be finite numbers, with no missing values.", "x")
        elif kind == "date":
            if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
                return None, error_result("INVALID_PLOT_X", "Date x values must strictly match YYYY-MM-DD.", "x")
            try:
                key = date.fromisoformat(value).toordinal()
            except ValueError:
                return None, error_result("INVALID_PLOT_X", "Date x values must be valid calendar dates.", "x")
        points.append({"source_index": index, "x": value, "y": row[request.y],
                       "x_sort_key": key,
                       "display_x": missing_label if value is None else str(value),
                       "display_y": _display_y(row[request.y], request)})
    if request.chart_type == "line":
        points.sort(key=lambda point: point["x_sort_key"])
    return points, None


def _render_png(request, points):
    # Web-server figures use the OO API and an in-memory buffer, avoiding
    # pyplot's global figure registry:
    # https://matplotlib.org/stable/gallery/user_interfaces/web_application_server_sgskip.html
    figure = Figure(figsize=(8, 4.8), dpi=120, layout="constrained")
    FigureCanvasAgg(figure)
    try:
        axes = figure.subplots()
        values = [point["y"] if point["y"] is not None else math.nan for point in points]
        if request.chart_type == "bar":
            # Explicit positions retain duplicate labels as separate bars.
            positions = list(range(len(points)))
            axes.bar(positions, values, color="#3569a8")
            axes.set_xticks(positions, [point["display_x"] for point in points], rotation=30, ha="right")
        else:
            kind = request.x_kind or "numeric"
            positions = [date.fromordinal(point["x_sort_key"]) if kind == "date"
                         else point["x_sort_key"] for point in points]
            axes.plot(positions, values, marker="o", color="#3569a8")
            if kind == "date":
                # The date view is parsed locally; source strings remain intact.
                from matplotlib.dates import DateFormatter, date2num

                # Use a bounded selection of actual calendar days. Automatic
                # sub-day ticks repeat when formatted as date-only labels.
                unique_dates = sorted(set(positions))
                step = max(1, math.ceil((len(unique_dates) - 1) / 6))
                tick_dates = unique_dates[::step]
                if tick_dates[-1] != unique_dates[-1]:
                    tick_dates.append(unique_dates[-1])
                axes.xaxis.set_major_locator(FixedLocator(date2num(tick_dates)))
                axes.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
                # Matplotlib's ordinary margins can cross year 1/9999 and
                # make valid ISO inputs fail during date tick conversion.
                lower, upper = date2num(unique_dates[0]), date2num(unique_dates[-1])
                margin = max(0.5, (upper - lower) * 0.05)
                axes.set_xlim(max(date2num(date.min), lower - margin),
                              min(date2num(date.max), upper + margin))
                figure.autofmt_xdate(rotation=30, ha="right")
        axes.set(title=request.title, xlabel=request.x_label, ylabel=request.y_label)
        # The axis and metadata share one display-only rounding operation.
        # https://matplotlib.org/stable/api/ticker_api.html#matplotlib.ticker.FuncFormatter
        axes.yaxis.set_major_formatter(FuncFormatter(lambda value, position: _display_y(value, request)))
        axes.set_axisbelow(True)
        axes.grid(axis="y", alpha=0.2)
        with BytesIO() as output:
            figure.savefig(output, format="png")
            return output.getvalue()
    finally:
        figure.clear()


def plot_result(session, arguments: dict | PlotRequest) -> dict:
    """Validate, resolve, render and register a complete chart in one context."""
    try:
        values = arguments.model_dump() if isinstance(arguments, PlotRequest) else arguments
        request = PlotRequest.model_validate(values)
    except ValidationError as exc:
        first = exc.errors(include_input=False)[0]
        field = ".".join(str(part) for part in first["loc"]) or "arguments"
        return error_result("INVALID_PLOT_FORMAT", first["msg"], field, "schema")
    response = session.resolve_result(request.result_id)
    if not response["success"]:
        return response
    source = response["data"]
    fields = {field["name"]: field["logical_type"] for field in source["fields"]}
    for name in ("x", "y"):
        if getattr(request, name) not in fields:
            return error_result("INVALID_PLOT_FIELD", "The selected field does not exist in this result.", name)
    if fields[request.y] != "numeric":
        return error_result("INVALID_PLOT_Y", "The y field must be numeric.", "y")
    rows = source["rows"]
    if not rows:
        return error_result("NO_PLOTTABLE_DATA", "This result contains no rows to plot.", "result_id")
    if any(row[request.y] is not None and (type(row[request.y]) not in (int, float)
                                         or not math.isfinite(row[request.y])) for row in rows):
        return error_result("INVALID_PLOT_Y", "The y field must contain finite numbers or missing values.", "y")
    if all(row[request.y] is None for row in rows):
        return error_result("NO_PLOTTABLE_DATA", "The y field has no non-missing numeric values.", "y")
    points, failure = _x_points(rows, request)
    if failure:
        return failure
    warnings = []
    if any(point["y"] is None for point in points):
        warnings.append({"code": "MISSING_PLOT_Y", "message": "Missing y values are retained as gaps; they were not replaced with zero."})
    try:
        # CSV labels are literal text, including dollar signs and backslashes.
        # Scope and restore rcParams; the render lock protects this global API.
        # https://matplotlib.org/stable/api/matplotlib_configuration_api.html#matplotlib.rc_context
        with _RENDER_LOCK:
            font_config = _font_config([request.title, request.x_label, request.y_label,
                                        *(point["display_x"] for point in points)])
            with rc_context({"text.parse_math": False, "text.usetex": False, **font_config}):
                png_bytes = _render_png(request, points)
    except (ValueError, TypeError, OverflowError, RuntimeError):
        return error_result("PLOT_RENDER_ERROR", "The chart could not be rendered.", "chart", "execution")
    chart_id = str(uuid4())
    data = {name: source[name] for name in ("result_id", "session_id", "dataset_id", "run_id")}
    data.update({name: getattr(request, name) for name in ("chart_type", "x", "y", "title", "x_label", "y_label")})
    data.update({"chart_id": chart_id,
                 "format": {"x_kind": request.x_kind or ("category" if request.chart_type == "bar" else "numeric"),
                            "date_format": request.date_format, "y_format": request.y_format,
                            "decimal_places": request.decimal_places, "unit": request.unit},
                 "plot_data": points,
                 "source": {name: source[name] for name in ("fields", "operations", "filtered_row_count")},
                 "artifact": {"format": "png", "mime_type": "image/png", "filename": f"{chart_id}.png", "size_bytes": len(png_bytes)}})
    return session.publish_chart({"success": True, "data": data, "error": None, "warnings": warnings}, png_bytes)
