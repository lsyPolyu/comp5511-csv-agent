"""Operate real statistics and chart forms; compare independent numeric facts."""

from copy import deepcopy
from inspect import getmodule, getsourcefile, signature
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def survival_page(*, language="en", alias="rate"):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    if language != "en":
        app.radio(key="ui_language").set_value(language).run()
    app.file_uploader[0].upload("sample.csv", (ROOT / "data/dev/eight_rows.csv").read_bytes(), "text/csv").run()
    app.multiselect(key="stats_groups").select("Sex")
    app.selectbox(key="stats_operation_0").select("mean")
    app.selectbox(key="stats_column_0").select("Survived")
    app.text_input(key="stats_alias_0").set_value(alias)
    app.button(key="stats_submit").click().run()
    assert not app.exception
    return app


def generate(app):
    app.button(key="chart_submit").click().run()
    assert not app.exception
    return app.session_state["_analysis_state"]


def test_real_statistics_to_bar_and_rerun_does_not_recalculate():
    app = survival_page()
    session = app.session_state["_analysis_state"]
    run_id, result_id = session.run_id, session.current_result_id
    session = generate(app)
    assert not app.error
    chart = session.current_chart()["data"]
    assert chart["chart_type"] == "bar"
    assert [(row["x"], row["y"]) for row in chart["plot_data"]] == [("female", 0.75), ("male", 0.25)]
    assert chart["result_id"] == result_id and chart["run_id"] == run_id
    assert session.chart_bytes(chart["chart_id"]).startswith(b"\x89PNG\r\n\x1a\n")
    assert len(app.dataframe) == 4
    assert len(app.get("download_button")) == 1
    chart_id = chart["chart_id"]
    app.run()
    assert app.session_state["_analysis_state"].current_chart()["data"]["chart_id"] == chart_id
    assert app.session_state["_analysis_state"].run_id == run_id


def test_percentage_changes_display_only():
    app = survival_page()
    app.selectbox(key="chart_y_format").select("percent")
    app.text_input(key="chart_unit").set_value("fraction")
    app.text_input(key="chart_y_label").set_value("Survival rate (%)")
    session = generate(app)
    assert not app.error
    chart = session.current_chart()["data"]
    assert [row["y"] for row in chart["plot_data"]] == [0.75, 0.25]
    assert [row["display_y"] for row in chart["plot_data"]] == ["75.00%", "25.00%"]
    assert chart["format"]["unit"] == "fraction"
    assert session.current_result()["data"]["rows"] == [{"Sex": "female", "rate": 0.75}, {"Sex": "male", "rate": 0.25}]


def revenue_page(*, dates=False):
    key = "Date" if dates else "Year"
    content = (b"Date,Revenue\n2026-01-03,30\n2026-01-01,10\n2026-01-02,20\n" if dates
               else b"Year,Revenue\n2022,30\n2020,10\n2021,20\n")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    app.file_uploader[0].upload("revenue.csv", content, "text/csv").run()
    app.number_input(key="stats_sort_count").set_value(1).run()
    app.multiselect(key="stats_groups").select(key)
    app.selectbox(key="stats_operation_0").select("sum")
    app.selectbox(key="stats_column_0").select("Revenue")
    app.text_input(key="stats_alias_0").set_value("Revenue")
    app.text_input(key="stats_sort_field_0").set_value(key)
    app.selectbox(key="stats_sort_direction_0").select("desc")
    app.button(key="stats_submit").click().run()
    assert not app.exception
    return app


@pytest.mark.parametrize("dates", [False, True])
def test_line_sorts_actual_result_without_reaggregating(dates):
    app = revenue_page(dates=dates)
    session = app.session_state["_analysis_state"]
    before = session.current_result()
    app.selectbox(key="chart_type").select("line")
    app.text_input(key="chart_title").set_value("Revenue trend")
    app.text_input(key="chart_x_label").set_value("Date" if dates else "Year")
    app.text_input(key="chart_y_label").set_value("Revenue")
    if dates:
        app.selectbox(key="chart_x_kind").select("date")
        app.text_input(key="chart_date_format").set_value("%Y-%m-%d")
    session = generate(app)
    assert not app.error
    chart = session.current_chart()["data"]
    assert [row["x"] for row in chart["plot_data"]] == (["2026-01-01", "2026-01-02", "2026-01-03"] if dates else [2020, 2021, 2022])
    assert [row["y"] for row in chart["plot_data"]] == [10, 20, 30]
    assert [row["source_index"] for row in chart["plot_data"]] == [2, 1, 0]
    assert chart["title"] == "Revenue trend" and chart["y_label"] == "Revenue"
    assert chart["format"]["date_format"] == ("%Y-%m-%d" if dates else None)
    assert session.current_result() == before


def test_invalid_chart_attempt_keeps_last_success_without_claiming_new_success():
    app = survival_page()
    session = generate(app)
    previous = session.current_chart()
    result = session.current_result()
    app.selectbox(key="chart_y_format").select("percent")
    session = generate(app)
    assert "INVALID_PLOT_FORMAT" in app.error[0].value
    assert session.current_chart() == previous
    assert session.current_result() == result
    assert any("Last successful chart" in item.value for item in app.caption)


def test_new_statistics_invalidates_chart_and_download_without_extra_calculation():
    app = survival_page()
    session = generate(app)
    old_chart = session.current_chart()["data"]["chart_id"]
    app.text_input(key="stats_alias_0").set_value("new_rate")
    app.button(key="stats_submit").click().run()
    assert not app.exception
    session = app.session_state["_analysis_state"]
    assert session.current_chart() is None
    assert session.chart_bytes(old_chart) is None
    assert not session.resolve_chart(old_chart)["success"]
    assert not app.get("download_button") and not app.image
    assert list(app.dataframe[2].value.columns) == ["Sex", "new_rate"]


@pytest.mark.parametrize("replacement", [b"A,B\n", b"A,B\n1,2,3\n", b"City,Value\nLondon,2\n", None])
def test_replacement_failure_or_clear_removes_chart_and_download(replacement):
    app = survival_page()
    session = generate(app)
    old_chart = session.current_chart()["data"]["chart_id"]
    if replacement is None:
        app.file_uploader[0].clear().run()
    else:
        app.file_uploader[0].upload("replacement.csv", replacement, "text/csv").run()
    assert not app.exception
    session = app.session_state["_analysis_state"]
    assert session.current_chart() is None and session.chart_bytes(old_chart) is None
    assert not app.get("download_button") and not app.image
    assert len(app.dataframe) <= 2


def test_download_widget_receives_exact_registered_png(monkeypatch):
    captured = []
    original = st.download_button

    def record(label, data, **kwargs):
        captured.append((label, data, kwargs))
        return original(label, data, **kwargs)

    monkeypatch.setattr(st, "download_button", record)
    app = survival_page()
    session = generate(app)
    chart = session.current_chart()["data"]
    assert len(app.image) == 1 and len(captured) == 1
    label, data, kwargs = captured[0]
    assert label == "Download chart (PNG)"
    assert data == session.chart_bytes(chart["chart_id"])
    assert kwargs["file_name"] == chart["artifact"]["filename"]
    assert kwargs["mime"] == "image/png" and kwargs["on_click"] == "ignore"
    result_id, run_id = session.current_result_id, session.run_id
    app.download_button[0].click().run()
    session = app.session_state["_analysis_state"]
    assert session.run_id == run_id and session.current_result_id == result_id
    assert session.current_chart()["data"]["chart_id"] == chart["chart_id"]


def test_p02_server_state_survives_the_plotting_upgrade():
    class P02Session:
        """An old server object retained by a pre-upgrade Streamlit session."""

    app = survival_page()
    current = app.session_state["_analysis_state"]
    before = current.current_result()
    legacy = P02Session()
    legacy.__dict__.update({key: value for key, value in current.__dict__.items()
                            if key not in ("_chart", "current_chart_id")})
    app.session_state["_analysis_state"] = legacy
    app.run()
    assert not app.exception
    session = generate(app)
    assert session.current_result() == before
    assert session.current_chart()["data"]["result_id"] == before["data"]["result_id"]


def test_two_page_sessions_cannot_read_or_draw_each_others_results():
    from comp5511.plotting import plot_result

    first = generate(survival_page())
    second = generate(survival_page())
    owned = first.current_chart()["data"]
    assert not second.resolve_chart(owned["chart_id"])["success"]
    assert second.chart_bytes(owned["chart_id"]) is None
    foreign = plot_result(second, {"result_id": owned["result_id"], "chart_type": "bar",
        "x": "Sex", "y": "rate", "title": "Other result", "x_label": "Sex", "y_label": "Rate"})
    assert foreign["error"]["code"] == "INVALID_RESULT_REFERENCE"
    assert second.current_chart()["data"]["result_id"] == second.current_result_id


def test_invalid_new_statistics_also_removes_old_chart():
    app = survival_page()
    session = generate(app)
    old_chart = session.current_chart()["data"]["chart_id"]
    app.selectbox(key="stats_column_0").select("Sex")
    app.button(key="stats_submit").click().run()
    assert not app.exception
    assert "INCOMPATIBLE_AGGREGATION" in app.error[0].value
    session = app.session_state["_analysis_state"]
    assert session.chart_bytes(old_chart) is None and session.current_chart() is None
    assert not app.image and not app.download_button


def has_chinese(value):
    return any("\u4e00" <= character <= "\u9fff" for character in value)


@pytest.mark.parametrize("initial_language", ["en", "zh"])
def test_uploaded_app_entry_calls_real_localized_renderers_and_preserves_context(monkeypatch, initial_language):
    """Exercise app.py imports and calls, then submit in both session languages."""
    from comp5511 import chart_ui, datasets, statistics_ui

    entries = []
    calls = {"load": 0, "aggregate": 0, "plot": 0}

    def localized_entry(name, original):
        original_signature = signature(original)
        source = Path(getmodule(original).__file__).resolve()
        assert source == Path(getsourcefile(original)).resolve()
        assert source == ROOT / "comp5511" / f"{name}_ui.py"

        def entry(session, *, language="en"):
            # A named language is the app/renderer contract. Invoke the real
            # renderer after binding its actual signature; no UI/business stub.
            bound = original_signature.bind(session, language=language)
            entries.append((name, bound.arguments["language"], source))
            return original(*bound.args, **bound.kwargs)

        return entry

    def count(name, original):
        def counted(*args, **kwargs):
            calls[name] += 1
            return original(*args, **kwargs)
        return counted

    monkeypatch.setattr(statistics_ui, "render_statistics", localized_entry("statistics", statistics_ui.render_statistics))
    monkeypatch.setattr(chart_ui, "render_charts", localized_entry("chart", chart_ui.render_charts))
    monkeypatch.setattr(datasets, "load_csv", count("load", datasets.load_csv))
    monkeypatch.setattr(statistics_ui, "aggregate_data", count("aggregate", statistics_ui.aggregate_data))
    monkeypatch.setattr(chart_ui, "plot_result", count("plot", chart_ui.plot_result))

    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    assert not app.exception
    assert app.radio(key="ui_language").value == "en"
    if initial_language != "en":
        app.radio(key="ui_language").set_value(initial_language).run()
    csv = (ROOT / "data/dev/eight_rows.csv").read_bytes()
    app.file_uploader[0].upload("sample.csv", csv, "text/csv").run()
    assert not app.exception
    # Check the actual two imported entry points immediately after upload,
    # before helpers or a successful statistics submission could mask failure.
    assert [(name, language) for name, language, _ in entries[-2:]] == [
        ("statistics", initial_language), ("chart", initial_language),
    ]
    assert app.button(key="stats_submit").label == ("Run statistics" if initial_language == "en" else "运行统计")
    assert calls == {"load": 1, "aggregate": 0, "plot": 0}

    app.multiselect(key="stats_groups").select("Sex")
    app.selectbox(key="stats_operation_0").select("mean")
    app.selectbox(key="stats_column_0").select("Survived")
    app.text_input(key="stats_alias_0").set_value("rate")
    app.button(key="stats_submit").click().run()
    assert not app.exception and not app.error
    session = app.session_state["_analysis_state"]
    expected_rows = [{"Sex": "female", "rate": 0.75}, {"Sex": "male", "rate": 0.25}]
    assert session.current_result()["data"]["rows"] == expected_rows
    app.selectbox(key="chart_y_format").select("percent").run()
    app.text_input(key="chart_unit").set_value("fraction")
    app.text_input(key="chart_x_label").set_value("Original Sex")
    session = generate(app)
    assert not app.error
    result, chart = deepcopy(session.current_result()), deepcopy(session.current_chart())
    assert [(row["x"], row["y"], row["display_y"]) for row in chart["data"]["plot_data"]] == [
        ("female", 0.75, "75.00%"), ("male", 0.25, "25.00%"),
    ]
    identity = (session.session_id, session.dataset.dataset_id, session.run_id,
                session.current_result_id, session.current_chart_id)
    png = session.chart_bytes(session.current_chart_id)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert calls == {"load": 1, "aggregate": 1, "plot": 1}
    parameters = {key: app.session_state[key] for key in (
        "stats_groups", "stats_operation_0", "stats_column_0", "stats_alias_0",
        "chart_source", "chart_type", "chart_x", "chart_y", "chart_x_kind",
        "chart_y_format", "chart_decimals", "chart_unit", "chart_x_label",
    )}

    next_language = "zh" if initial_language == "en" else "en"
    app.radio(key="ui_language").set_value(next_language).run()
    assert not app.exception and not app.error
    assert [(name, language) for name, language, _ in entries[-2:]] == [
        ("statistics", next_language), ("chart", next_language),
    ]
    assert {key: app.session_state[key] for key in parameters} == parameters
    # A real client retains serialized option strings between requests. The
    # server must explicitly replace old-language strings after a switch.
    for key, expected in {
        "stats_operation_0": "mean" if next_language == "en" else "平均值（mean）",
        "chart_y_format": "percent" if next_language == "en" else "百分比（percent）",
    }.items():
        assert app.selectbox(key=key).proto.set_value is True
        assert app.selectbox(key=key).proto.raw_value == expected
    session = app.session_state["_analysis_state"]
    assert (session.session_id, session.dataset.dataset_id, session.run_id,
            session.current_result_id, session.current_chart_id) == identity
    assert session.dataset.original_bytes == csv
    assert session.current_result() == result and session.current_chart() == chart
    assert session.chart_bytes(session.current_chart_id) == png
    assert len(app.download_button) == 1
    assert calls == {"load": 1, "aggregate": 1, "plot": 1}

    # Both entries continue to work after switching; explicit statistics creates
    # a new run and clears the old chart before the next explicit generation.
    app.button(key="stats_submit").click().run()
    assert not app.exception and not app.error
    session = app.session_state["_analysis_state"]
    assert session.session_id == identity[0] and session.dataset.dataset_id == identity[1]
    assert session.run_id != identity[2] and session.current_result_id != identity[3]
    assert session.current_result()["data"]["rows"] == expected_rows
    assert session.current_chart() is None and session.chart_bytes(identity[4]) is None
    assert not app.image and not app.download_button
    app.selectbox(key="chart_y_format").select("percent").run()
    app.text_input(key="chart_unit").set_value("fraction")
    session = generate(app)
    assert not app.error
    regenerated = session.current_chart()["data"]
    assert regenerated["chart_id"] != identity[4]
    assert regenerated["result_id"] == session.current_result_id
    assert regenerated["run_id"] == session.run_id
    assert regenerated["title"] == ("Analysis result" if next_language == "en" else "统计结果")
    assert regenerated["y_label"] == ("Value (%)" if next_language == "en" else "数值 (%)")
    assert [row["y"] for row in regenerated["plot_data"]] == [0.75, 0.25]
    assert calls == {"load": 1, "aggregate": 2, "plot": 2}
    print(f"Actual app.py entry verified: {initial_language} -> {next_language}; "
          f"sources={sorted({str(source) for _, _, source in entries})}; calls={calls}")


def test_language_defaults_to_english_and_chinese_session_completes_real_flow(monkeypatch):
    captured = []
    original = st.download_button

    def record(label, data, **kwargs):
        captured.append((label, data, kwargs))
        return original(label, data, **kwargs)

    monkeypatch.setattr(st, "download_button", record)
    english = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    assert english.radio(key="ui_language").value == "en"
    assert english.radio(key="ui_language").options == ["English", "中文"]
    assert english.title[0].value == "CSV Dataset Inspector"

    # An alias, source column, and category are data, even if their text is Chinese.
    app = survival_page(language="zh", alias="原样 rate")
    assert not app.error
    assert app.radio(key="ui_language").value == "zh"
    assert has_chinese(app.title[0].value)
    assert has_chinese(app.file_uploader[0].label)
    assert has_chinese(app.button(key="stats_submit").label)
    assert any("mean" in option and has_chinese(option)
               for option in app.selectbox(key="stats_operation_0").options)
    session = app.session_state["_analysis_state"]
    assert session.dataset.headers == ("Sex", "Survived", "Age")
    assert session.dataset.original_bytes == (ROOT / "data/dev/eight_rows.csv").read_bytes()
    result = session.current_result()
    assert result["data"]["rows"] == [
        {"Sex": "female", "原样 rate": 0.75}, {"Sex": "male", "原样 rate": 0.25},
    ]
    assert list(app.dataframe[0].value.columns) == ["Sex", "Survived", "Age"]
    assert all(has_chinese(column) for column in app.dataframe[1].value.columns)
    assert list(app.dataframe[2].value.columns) == ["Sex", "原样 rate"]
    app.selectbox(key="chart_y_format").select("percent").run()
    app.text_input(key="chart_unit").set_value("fraction")
    session = generate(app)
    assert not app.error
    chart = session.current_chart()["data"]
    assert chart["result_id"] == result["data"]["result_id"]
    assert chart["x"] == "Sex" and chart["y"] == "原样 rate"
    assert [(row["x"], row["y"], row["display_y"]) for row in chart["plot_data"]] == [
        ("female", 0.75, "75.00%"), ("male", 0.25, "25.00%"),
    ]
    assert chart["y_label"] == "数值 (%)"
    assert has_chinese(captured[-1][0])
    assert captured[-1][1] == session.chart_bytes(chart["chart_id"])
    assert captured[-1][2]["file_name"] == chart["chart_id"] + ".png"
    app.download_button[0].click().run()
    assert not app.exception
    assert app.session_state["_analysis_state"].current_chart()["data"] == chart
    english.run()
    assert english.radio(key="ui_language").value == "en"
    assert english.session_state["_analysis_state"].dataset is None


def test_language_switch_preserves_pending_controls_and_artifacts_without_execution(monkeypatch):
    from comp5511 import chart_ui, datasets, statistics_ui

    calls = {"load": 0, "aggregate": 0, "plot": 0}

    def count(name, function):
        def wrapper(*args, **kwargs):
            calls[name] += 1
            return function(*args, **kwargs)
        return wrapper

    monkeypatch.setattr(datasets, "load_csv", count("load", datasets.load_csv))
    monkeypatch.setattr(statistics_ui, "aggregate_data", count("aggregate", statistics_ui.aggregate_data))
    monkeypatch.setattr(chart_ui, "plot_result", count("plot", chart_ui.plot_result))
    app = survival_page()
    session = generate(app)
    dataset, result, chart = session.dataset, session.current_result(), session.current_chart()
    identity = (session.session_id, dataset.dataset_id, session.run_id,
                session.current_result_id, session.current_chart_id)
    png = session.chart_bytes(session.current_chart_id)
    assert calls == {"load": 1, "aggregate": 1, "plot": 1}
    app.number_input(key="stats_filter_count").set_value(1)
    app.number_input(key="stats_metric_count").set_value(2)
    app.number_input(key="stats_sort_count").set_value(1).run()
    app.selectbox(key="stats_filter_column_0").select("Age")
    app.selectbox(key="stats_filter_op_0").select("ge")
    app.text_area(key="stats_filter_value_0").set_value("20")
    app.selectbox(key="stats_operation_0").select("sum")
    app.text_input(key="stats_alias_0").set_value("pending_alias")
    app.text_input(key="stats_sort_field_0").set_value("pending_alias")
    app.selectbox(key="stats_sort_direction_0").select("desc")
    app.selectbox(key="chart_type").select("line")
    app.selectbox(key="chart_x_kind").select("date")
    app.text_input(key="chart_date_format").set_value("%Y-%m-%d")
    app.selectbox(key="chart_y_format").select("percent")
    app.number_input(key="chart_decimals").set_value(4)
    app.text_input(key="chart_unit").set_value("fraction").run()
    pending = {
        "stats_filter_count": 1, "stats_metric_count": 2, "stats_sort_count": 1, "stats_groups": ["Sex"],
        "stats_filter_column_0": "Age", "stats_filter_op_0": "ge", "stats_filter_value_0": "20",
        "stats_operation_0": "sum", "stats_column_0": "Survived", "stats_alias_0": "pending_alias",
        "stats_operation_1": "row_count", "stats_column_1": None,
        "stats_sort_field_0": "pending_alias", "stats_sort_direction_0": "desc",
        "chart_source": result["data"]["result_id"], "chart_type": "line", "chart_x": "Sex",
        "chart_y": "rate", "chart_x_kind": "date", "chart_date_format": "%Y-%m-%d",
        "chart_y_format": "percent", "chart_decimals": 4, "chart_unit": "fraction",
    }
    for language in ("zh", "en"):
        app.radio(key="ui_language").set_value(language).run()
        assert not app.exception
        assert {key: app.session_state[key] for key in pending} == pending
        for key, labels in {
            "stats_filter_op_0": ("ge", "大于或等于（ge）"),
            "stats_operation_0": ("sum", "求和（sum）"),
            "stats_sort_direction_0": ("desc", "降序（desc）"),
            "chart_type": ("line", "折线图（line）"),
            "chart_x_kind": ("date", "日期（date）"),
            "chart_y_format": ("percent", "百分比（percent）"),
        }.items():
            proto = app.selectbox(key=key).proto
            assert proto.set_value is True
            assert proto.raw_value == labels[0 if language == "en" else 1]
        # Streamlit serializes None as an unset raw_value, not its display label.
        column_proto = app.selectbox(key="stats_column_1").proto
        assert column_proto.set_value is True and column_proto.raw_value == ""
        assert column_proto.options[0] == ("No column (row_count)" if language == "en" else "无列（row_count）")
        session = app.session_state["_analysis_state"]
        assert (session.session_id, session.dataset.dataset_id, session.run_id,
                session.current_result_id, session.current_chart_id) == identity
        assert session.dataset == dataset
        assert session.current_result() == result and session.current_chart() == chart
        assert session.chart_bytes(session.current_chart_id) == png
        assert calls == {"load": 1, "aggregate": 1, "plot": 1}
        assert len(app.download_button) == 1


def test_language_defaults_change_only_unedited_labels_and_explicitly_generated_chart():
    app = survival_page()
    session = generate(app)
    original = session.current_chart()
    old_png = session.chart_bytes(session.current_chart_id)
    assert [app.text_input(key=key).value for key in ("chart_title", "chart_x_label", "chart_y_label")] == [
        "Analysis result", "X value", "Value",
    ]
    app.radio(key="ui_language").set_value("zh").run()
    assert [app.text_input(key=key).value for key in ("chart_title", "chart_x_label", "chart_y_label")] == [
        "统计结果", "X 值", "数值",
    ]
    session = app.session_state["_analysis_state"]
    assert session.current_chart() == original
    assert session.chart_bytes(session.current_chart_id) == old_png
    app.selectbox(key="chart_y_format").select("percent").run()
    assert app.text_input(key="chart_y_label").value == "数值 (%)"
    app.text_input(key="chart_unit").set_value("fraction")
    session = generate(app)
    translated = session.current_chart()["data"]
    assert (translated["title"], translated["x_label"], translated["y_label"]) == ("统计结果", "X 值", "数值 (%)")
    assert translated["chart_id"] != original["data"]["chart_id"]
    assert translated["result_id"] == original["data"]["result_id"]
    custom = {"chart_title": "用户 title", "chart_x_label": "原始 Sex", "chart_y_label": "Custom rate (%)"}
    for key, value in custom.items():
        app.text_input(key=key).set_value(value)
    app.run()
    for language in ("en", "zh"):
        app.radio(key="ui_language").set_value(language).run()
        assert not app.exception
        assert {key: app.text_input(key=key).value for key in custom} == custom
        assert app.session_state["_analysis_state"].current_chart()["data"] == translated


@pytest.mark.parametrize("error_kind", ["statistics", "chart"])
def test_chinese_error_explanation_keeps_original_code_and_error_data(error_kind):
    app = survival_page(language="zh")
    session = generate(app)
    if error_kind == "statistics":
        app.selectbox(key="stats_column_0").select("Sex")
        app.button(key="stats_submit").click().run()
        error_key, code = "_statistics_error", "INCOMPATIBLE_AGGREGATION"
    else:
        app.selectbox(key="chart_y_format").select("percent")
        app.button(key="chart_submit").click().run()
        error_key, code = "_chart_error", "INVALID_PLOT_FORMAT"
    assert not app.exception
    error = deepcopy(app.session_state[error_key])
    assert error["code"] == code
    assert any(code in item.value and has_chinese(item.value) for item in app.error)
    assert not has_chinese(error["message"])
    after_error = (session.current_result(), session.current_chart(), session.run_id)
    app.radio(key="ui_language").set_value("en").run()
    assert not app.exception
    assert app.session_state[error_key] == error
    assert any(code in item.value and error["message"] in item.value for item in app.error)
    assert (session.current_result(), session.current_chart(), session.run_id) == after_error


@pytest.mark.parametrize("replacement", [b"City,Value\nLondon,2\n", b"A,B\n1,2,3\n"])
def test_chinese_upload_replacement_still_invalidates_old_chart(replacement):
    app = survival_page(language="zh")
    session = generate(app)
    old_chart = session.current_chart_id
    app.file_uploader[0].upload("replacement.csv", replacement, "text/csv").run()
    assert not app.exception
    assert app.radio(key="ui_language").value == "zh"
    session = app.session_state["_analysis_state"]
    assert session.current_chart() is None and session.chart_bytes(old_chart) is None
    assert not app.image and not app.download_button
    if app.error:
        assert "CSV_PARSE_ERROR" in app.error[0].value and has_chinese(app.error[0].value)
