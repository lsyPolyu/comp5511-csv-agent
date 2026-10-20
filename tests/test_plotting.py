"""P03 chart contracts and hand-calculated data; no pixel equality checks."""

from datetime import date
import json
import math
from pathlib import Path
import warnings

from matplotlib import font_manager, rcParams
from matplotlib.figure import Figure
from matplotlib.ft2font import FT2Font
from matplotlib._pylab_helpers import Gcf
import pytest

from comp5511.analysis import aggregate_data
from comp5511.contracts import PlotRequest
from comp5511.datasets import load_csv
from comp5511.plotting import _display_y, _font_config, plot_result
from comp5511.state import AnalysisSession


def session_result(content=None, *, group_by=None, metrics=None, **operations):
    session = AnalysisSession()
    content = content or (Path(__file__).resolve().parents[1] / "data/dev/eight_rows.csv").read_bytes()
    session.replace_dataset(load_csv(content, "sample.csv"))
    session.begin_run()
    result = session.publish_result(aggregate_data(session.dataset, {
        "group_by": group_by or ["Sex"],
        "metrics": metrics or [{"operation": "mean", "column": "Survived", "alias": "Rate"}],
        **operations,
    }, session_id=session.session_id, run_id=session.run_id))
    assert result["success"], result
    return session, result["data"]


def arguments(result, **changes):
    return {"result_id": result["result_id"], "chart_type": "bar", "x": "Sex", "y": "Rate",
            "title": "Survival by sex", "x_label": "Sex", "y_label": "Survival rate (fraction)",
            "unit": "fraction", **changes}


def test_bar_hand_calculated_data_and_in_memory_artifact():
    session, result = session_result()
    response = plot_result(session, arguments(result))
    assert response["success"], response
    data = response["data"]
    assert [(point["x"], point["y"], point["display_y"]) for point in data["plot_data"]] == [
        ("female", 0.75, "0.75"), ("male", 0.25, "0.25")]
    assert [point["source_index"] for point in data["plot_data"]] == [0, 1]
    assert data["result_id"] == result["result_id"]
    assert data["format"] == {"x_kind": "category", "date_format": None, "y_format": "number", "decimal_places": 2, "unit": "fraction"}
    assert data["source"]["operations"] == result["operations"]
    png = session.chart_bytes(data["chart_id"])
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert data["artifact"]["size_bytes"] == len(png)


def test_percent_changes_display_only():
    session, result = session_result()
    response = plot_result(session, arguments(result, y_format="percent", y_label="Survival rate (%)"))
    assert response["success"], response
    assert [(row["y"], row["display_y"]) for row in response["data"]["plot_data"]] == [(0.75, "75.00%"), (0.25, "25.00%")]
    assert session.resolve_result(result["result_id"])["data"] == result


@pytest.mark.parametrize("value,expected", [
    (5e-324, "0.00%"), (0.00004999, "0.00%"), (0.00005, "0.00%"),
    (0.00005001, "0.01%"), (0.00015, "0.02%"),
    (-0.00005, "-0.00%"), (-0.00005001, "-0.01%"),
    (0.75, "75.00%"), (0.25, "25.00%"),
    (1e20, "10000000000000000000000.00%")])
def test_percent_axis_and_metadata_share_rounding_without_changing_values(value, expected, monkeypatch):
    session, result = session_result(f"Category,Value\na,{value}\n".encode(), group_by=["Category"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}])
    captured = []
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        axes = figure.axes[0]
        captured.append((axes.yaxis.get_major_formatter()(value), axes.patches[0].get_height()))
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    response = plot_result(session, arguments(result, x="Category", y="Total", y_format="percent", y_label="Value (%)"))
    assert response["success"], response
    assert captured == [(expected, value)]
    assert response["data"]["plot_data"][0]["display_y"] == expected
    assert response["data"]["plot_data"][0]["y"] == value


def test_large_finite_percent_display_does_not_overflow_to_infinity():
    request = PlotRequest(result_id="registered", chart_type="bar", x="Category", y="Value",
        title="Large value", x_label="Category", y_label="Value (%)", y_format="percent", unit="fraction")
    # 10**308 scaled for display is 10**310; no float multiplication is needed.
    assert _display_y(1e308, request) == "1" + "0" * 310 + ".00%"


@pytest.mark.parametrize("changes", [
    {"rows": [{"Sex": "female", "Rate": 1}]}, {"decimal_places": True}, {"decimal_places": -1},
    {"decimal_places": 7}, {"y_format": "percent", "unit": "unknown", "y_label": "Survival (%)"},
    {"y_format": "percent"}, {"title": " "}, {"title": "Title\nline"}, {"x_label": "\tAxis"},
    {"unit": "比例"}, {"chart_type": "pie"},
    {"date_format": "%Y-%m-%d"}, {"x_kind": "date"}, {"x_kind": "date", "date_format": "%d/%m/%Y"},
])
def test_invalid_format_is_rejected_before_chart_registration(changes):
    session, result = session_result()
    response = plot_result(session, arguments(result, **changes))
    assert response["success"] is False
    assert response["error"]["code"] == "INVALID_PLOT_FORMAT"
    assert response["error"]["error_stage"] == "schema"


def test_invalid_result_and_unknown_field_are_structured_errors():
    session, result = session_result()
    assert plot_result(session, arguments(result, result_id="missing"))["error"]["code"] == "INVALID_RESULT_REFERENCE"
    assert plot_result(session, arguments(result, x="Unknown"))["error"]["code"] == "INVALID_PLOT_FIELD"
    assert plot_result(session, arguments(result, y="Sex"))["error"]["code"] == "INVALID_PLOT_Y"


def test_rendered_bar_type_labels_values_and_percentage_formatter(monkeypatch):
    session, result = session_result()
    captured = {}
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        axes = figure.axes[0]
        captured.update(figure=figure, heights=[patch.get_height() for patch in axes.patches],
                        lines=len(axes.lines), title=axes.get_title(), xlabel=axes.get_xlabel(),
                        ylabel=axes.get_ylabel(), tick=axes.yaxis.get_major_formatter()(0.75),
                        xticks=[label.get_text() for label in axes.get_xticklabels()])
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    before = set(Gcf.figs)
    response = plot_result(session, arguments(result, y_format="percent", y_label="Survival rate (%)"))
    assert response["success"], response
    assert captured["heights"] == [0.75, 0.25]
    assert captured["lines"] == 0
    assert (captured["title"], captured["xlabel"], captured["ylabel"]) == (
        "Survival by sex", "Sex", "Survival rate (%)")
    assert captured["tick"] == "75.00%" and captured["xticks"] == ["female", "male"]
    assert captured["figure"].axes == []
    assert set(Gcf.figs) == before


def test_chinese_labels_and_original_csv_values_render_without_missing_glyphs(monkeypatch):
    content = "性别,生还\n女性,1\n女性,1\n女性,1\n女性,0\n男性,1\n男性,0\n男性,0\n男性,0\n".encode("utf-8")
    session, result = session_result(content, group_by=["性别"],
        metrics=[{"operation": "mean", "column": "生还", "alias": "平均生还率"}])
    before_fonts = list(rcParams["font.family"])
    captured = {}
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        axes = figure.axes[0]
        captured.update(title=axes.get_title(), xlabel=axes.get_xlabel(), ylabel=axes.get_ylabel(),
                        categories=[tick.get_text() for tick in axes.get_xticklabels()],
                        formatter=axes.yaxis.get_major_formatter()(0.75), fonts=list(rcParams["font.family"]))
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = plot_result(session, arguments(result, x="性别", y="平均生还率",
            title="按性别统计生还率", x_label="性别", y_label="平均生还率 (%)", y_format="percent"))
    assert response["success"], response
    assert not [warning for warning in caught if "Glyph" in str(warning.message) and "missing" in str(warning.message)]
    assert (captured["title"], captured["xlabel"], captured["ylabel"], captured["categories"], captured["formatter"]) == (
        "按性别统计生还率", "性别", "平均生还率 (%)", ["女性", "男性"], "75.00%")
    assert captured["fonts"][0] == "DejaVu Sans"
    selected = font_manager.findfont(font_manager.FontProperties(family=captured["fonts"][1]), fallback_to_default=False)
    assert set(map(ord, "按性别统计生还率平均女性男性")).issubset(FT2Font(selected).get_charmap())
    assert list(rcParams["font.family"]) == before_fonts
    data = response["data"]
    assert [(point["x"], point["y"], point["display_y"]) for point in data["plot_data"]] == [
        ("女性", 0.75, "75.00%"), ("男性", 0.25, "25.00%")]
    assert (data["x"], data["y"], data["title"], data["x_label"], data["y_label"]) == (
        "性别", "平均生还率", "按性别统计生还率", "性别", "平均生还率 (%)")
    assert session.resolve_result(result["result_id"])["data"] == result


def test_english_charts_keep_existing_fonts_and_missing_cjk_font_is_structured(monkeypatch):
    assert _font_config(["Survival by sex", "Sex", "Survival rate (%)", "female", "male"]) == {}
    original = font_manager.findfont

    def no_cjk_font(properties, **kwargs):
        if properties.get_family() != ["DejaVu Sans"]:
            raise ValueError("No matching local font")
        return original(properties, **kwargs)

    monkeypatch.setattr(font_manager, "findfont", no_cjk_font)
    session, result = session_result()
    response = plot_result(session, arguments(result, title="中文图表"))
    assert response["error"]["code"] == "PLOT_RENDER_ERROR"
    assert session.current_chart() is None


def test_bar_keeps_result_order_and_duplicate_x_labels_as_separate_bars(monkeypatch):
    session, result = session_result(b"Year,Category,Revenue\n2022,a,30\n2020,b,10\n2021,c,20\n2020,d,40\n",
        group_by=["Year", "Category"], metrics=[{"operation": "sum", "column": "Revenue", "alias": "Revenue"}],
        sort_by=[{"column": "Category", "direction": "asc"}])
    captured = []
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        captured.extend((patch.get_x(), patch.get_height()) for patch in figure.axes[0].patches)
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    response = plot_result(session, arguments(result, x="Year", y="Revenue", unit="USD", x_label="Year", y_label="Revenue (USD)"))
    assert response["success"], response
    assert [(row["x"], row["y"]) for row in response["data"]["plot_data"]] == [(2022, 30), (2020, 10), (2021, 20), (2020, 40)]
    assert [height for _, height in captured] == [30, 10, 20, 40]
    assert len({position for position, _ in captured}) == 4
    assert response["data"]["format"]["unit"] == "USD"


def test_numeric_line_sorts_stably_without_reaggregation(monkeypatch):
    session, result = session_result(b"Year,Category,Revenue\n2022,a,30\n2020,b,10\n2021,c,20\n2020,d,40\n",
        group_by=["Year", "Category"], metrics=[{"operation": "sum", "column": "Revenue", "alias": "Revenue"}],
        sort_by=[{"column": "Category", "direction": "asc"}])
    captured = {}
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        axes = figure.axes[0]
        captured.update(x=list(axes.lines[0].get_xdata()), y=list(axes.lines[0].get_ydata()), bars=len(axes.patches))
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    response = plot_result(session, arguments(result, chart_type="line", x="Year", y="Revenue", x_label="Year", y_label="Revenue"))
    assert response["success"], response
    points = response["data"]["plot_data"]
    assert [(point["source_index"], point["x"], point["y"]) for point in points] == [(1, 2020, 10), (3, 2020, 40), (2, 2021, 20), (0, 2022, 30)]
    assert captured == {"x": [2020, 2020, 2021, 2022], "y": [10, 40, 20, 30], "bars": 0}
    assert session.resolve_result(result["result_id"])["data"] == result
    json.dumps(response, allow_nan=False)


def test_iso_date_line_uses_parsed_sort_keys_and_preserves_source_strings(monkeypatch):
    session, result = session_result(b"Day,Category,Value\n2026-10-16,a,30\n2026-01-01,b,10\n2026-03-02,c,20\n",
        group_by=["Day", "Category"], metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}],
        sort_by=[{"column": "Category", "direction": "asc"}])
    captured = {}
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        axes = figure.axes[0]
        captured.update(x=list(axes.lines[0].get_xdata()),
                        calendar_positions=list(axes.lines[0].get_xdata(orig=False)),
                        date_format=axes.xaxis.get_major_formatter().fmt)
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    response = plot_result(session, arguments(result, chart_type="line", x="Day", y="Total", x_kind="date", date_format="%Y-%m-%d", x_label="Date", y_label="Total"))
    assert response["success"], response
    points = response["data"]["plot_data"]
    assert [(point["source_index"], point["x"], point["y"]) for point in points] == [
        (1, "2026-01-01", 10), (2, "2026-03-02", 20), (0, "2026-10-16", 30)]
    assert [point["x_sort_key"] for point in points] == [date(2026, 1, 1).toordinal(), date(2026, 3, 2).toordinal(), date(2026, 10, 16).toordinal()]
    assert captured["x"] == [date(2026, 1, 1), date(2026, 3, 2), date(2026, 10, 16)]
    assert captured["date_format"] == "%Y-%m-%d"
    positions = captured["calendar_positions"]
    # 2026 is not a leap year: Jan 1 to Mar 2 is 60 days; Mar 2 to Oct 16 is 228.
    assert [positions[1] - positions[0], positions[2] - positions[1]] == [60, 228]
    assert session.resolve_result(result["result_id"])["data"] == result


@pytest.mark.parametrize("days", [
    ["2026-01-01", "2026-01-02", "2026-01-03"],
    ["0001-01-01", "0001-01-02"],
    ["9999-12-30", "9999-12-31"],
    ["0001-01-01"],
    ["9999-12-31"],
    ["0001-01-01", "5000-01-01", "9999-12-31"],
])
def test_date_ticks_are_unique_iso_days_and_calendar_endpoints_render(days, monkeypatch):
    content = ("Day,Value\n" + "\n".join(f"{day},{index + 1}" for index, day in enumerate(days)) + "\n").encode()
    session, result = session_result(content, group_by=["Day"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}])
    captured = []
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        captured.extend(label.get_text() for label in figure.axes[0].get_xticklabels())
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    response = plot_result(session, arguments(result, chart_type="line", x="Day", y="Total", x_kind="date", date_format="%Y-%m-%d"))
    assert response["success"], response
    assert 1 <= len(captured) <= 7
    assert len(captured) == len(set(captured))
    assert all(date.fromisoformat(label).isoformat() == label for label in captured)
    assert [point["x"] for point in response["data"]["plot_data"]] == days


@pytest.mark.parametrize("invalid", ["", "2026-02-30", "15/10/2026", "2026-1-01", "2026-01-01T00:00:00", "0000-01-01"])
def test_invalid_date_values_are_not_guessed(invalid):
    session, result = session_result(f"Day,Value\n{invalid},1\n2026-01-01,2\n".encode(), group_by=["Day"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}])
    response = plot_result(session, arguments(result, chart_type="line", x="Day", y="Total", x_kind="date", date_format="%Y-%m-%d"))
    assert response["error"]["code"] == "INVALID_PLOT_X"


def test_null_category_labels_do_not_collide_with_literal_strings():
    session, result = session_result(b"Category,Value\n,1\n(missing),2\n(missing) [null],3\n", group_by=["Category"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}])
    response = plot_result(session, arguments(result, x="Category", y="Total"))
    assert response["success"], response
    points = response["data"]["plot_data"]
    assert [point["x"] for point in points] == ["(missing)", "(missing) [null]", None]
    assert [point["display_x"] for point in points] == ["(missing)", "(missing) [null]", "(missing) [null] [null]"]


def test_original_data_labels_are_literal_text_not_mathtext(monkeypatch):
    session, result = session_result(b"Category,Value\n$\\unknown$,1\n$100$,2\n", group_by=["Category"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}])
    captured = []
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        captured.extend((text.get_text(), text.get_parse_math(), text.get_usetex())
                        for text in figure.axes[0].get_xticklabels())
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    response = plot_result(session, arguments(result, x="Category", y="Total"))
    assert response["success"], response
    assert captured == [("$100$", False, False), ("$\\unknown$", False, False)]
    assert [point["x"] for point in response["data"]["plot_data"]] == ["$100$", "$\\unknown$"]


@pytest.mark.parametrize("chart_type", ["bar", "line"])
def test_missing_y_is_a_gap_not_zero(chart_type, monkeypatch):
    session, result = session_result(b"Year,Value\n2020,10\n2021,\n2022,30\n", group_by=["Year"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}])
    captured = []
    original = Figure.savefig

    def inspect_figure(figure, *args, **kwargs):
        axes = figure.axes[0]
        captured.extend(axes.lines[0].get_ydata() if chart_type == "line" else [patch.get_height() for patch in axes.patches])
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", inspect_figure)
    response = plot_result(session, arguments(result, chart_type=chart_type, x="Year", y="Total"))
    assert response["success"], response
    assert [(point["y"], point["display_y"]) for point in response["data"]["plot_data"]] == [(10, "10.00"), (None, None), (30, "30.00")]
    assert [warning["code"] for warning in response["warnings"]] == ["MISSING_PLOT_Y"]
    assert captured[0] == 10 and math.isnan(captured[1]) and captured[2] == 30


def test_null_or_text_numeric_x_and_empty_or_all_missing_y_fail():
    session, result = session_result(b"Year,Value\n2020,10\n,30\n", group_by=["Year"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}])
    assert plot_result(session, arguments(result, chart_type="line", x="Year", y="Total"))["error"]["code"] == "INVALID_PLOT_X"
    session, result = session_result()
    assert plot_result(session, arguments(result, chart_type="line"))["error"]["code"] == "INVALID_PLOT_X"
    session, result = session_result(b"Group,Value\na,\nb,10\n", group_by=["Group"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}], filters=[{"column": "Group", "op": "eq", "value": "a"}])
    assert plot_result(session, arguments(result, x="Group", y="Total"))["error"]["code"] == "NO_PLOTTABLE_DATA"
    session, result = session_result(b"Group,Value\na,10\n", group_by=["Group"],
        metrics=[{"operation": "sum", "column": "Value", "alias": "Total"}], filters=[{"column": "Value", "op": "gt", "value": 20}])
    assert plot_result(session, arguments(result, x="Group", y="Total"))["error"]["code"] == "NO_PLOTTABLE_DATA"


def test_context_isolation_and_model_instances_are_revalidated():
    session, result = session_result()
    other, _ = session_result()
    assert plot_result(other, arguments(result))["error"]["code"] == "INVALID_RESULT_REFERENCE"
    request = PlotRequest(**arguments(result))
    request.decimal_places = True
    assert plot_result(session, request)["error"]["code"] == "INVALID_PLOT_FORMAT"
    session.begin_run()
    assert plot_result(session, arguments(result))["error"]["code"] == "INVALID_RESULT_REFERENCE"
    session, result = session_result()
    session.replace_dataset(load_csv(b"Value\n1\n", "other.csv"))
    assert plot_result(session, arguments(result))["error"]["code"] == "INVALID_RESULT_REFERENCE"
    session, result = session_result()
    session.clear_dataset()
    assert plot_result(session, arguments(result))["error"]["code"] == "INVALID_RESULT_REFERENCE"


def test_render_failure_cleans_figure_and_keeps_prior_success(monkeypatch):
    session, result = session_result()
    successful = plot_result(session, arguments(result))
    captured = []

    def fail_save(figure, *args, **kwargs):
        captured.append(figure)
        raise ValueError("private internal render details")

    monkeypatch.setattr(Figure, "savefig", fail_save)
    failure = plot_result(session, arguments(result))
    assert failure["error"]["code"] == "PLOT_RENDER_ERROR"
    assert "private" not in failure["error"]["message"]
    assert captured[0].axes == []
    assert session.current_chart() == successful
