"""Actual form operations with hand-calculated expectations, without a model."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def uploaded_page(content=None):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=10).run()
    app.file_uploader[0].upload("sample.csv", content or (ROOT / "data/dev/eight_rows.csv").read_bytes(), "text/csv").run()
    assert not app.exception
    return app


def test_explicit_submission_runs_once_and_rerun_preserves_result():
    app = uploaded_page()
    assert len(app.dataframe) == 2
    assert app.session_state["_analysis_state"].run_id is None
    app.button(key="stats_submit").click().run()
    assert not app.exception
    assert app.dataframe[2].value.to_dict("records") == [{"rows": 8}]
    session = app.session_state["_analysis_state"]
    run_id, result_id = session.run_id, session.current_result_id
    app.run()
    assert not app.exception
    assert app.session_state["_analysis_state"].run_id == run_id
    assert app.session_state["_analysis_state"].current_result_id == result_id
    app.number_input(key="stats_metric_count").set_value(2).run()
    assert app.session_state["_analysis_state"].run_id == run_id
    assert app.session_state["_analysis_state"].current_result_id == result_id
    assert app.dataframe[2].value.to_dict("records") == [{"rows": 8}]


def test_grouped_survival_mean_is_real_calculation():
    app = uploaded_page()
    app.multiselect(key="stats_groups").select("Sex")
    app.selectbox(key="stats_operation_0").select("mean")
    app.selectbox(key="stats_column_0").select("Survived")
    app.text_input(key="stats_alias_0").set_value("survival_rate")
    app.button(key="stats_submit").click().run()
    assert not app.exception
    assert app.dataframe[2].value.to_dict("records") == [
        {"Sex": "female", "survival_rate": 0.75},
        {"Sex": "male", "survival_rate": 0.25},
    ]


def set_counts(app, *, filters=0, metrics=1, sorts=0):
    app.number_input(key="stats_filter_count").set_value(filters)
    app.number_input(key="stats_metric_count").set_value(metrics)
    app.number_input(key="stats_sort_count").set_value(sorts).run()
    assert not app.exception


def set_metric(app, index, operation, column, alias):
    app.selectbox(key=f"stats_operation_{index}").select(operation)
    app.selectbox(key=f"stats_column_{index}").select(column)
    app.text_input(key=f"stats_alias_{index}").set_value(alias)


def set_filter(app, index, column, op, value):
    app.selectbox(key=f"stats_filter_column_{index}").select(column)
    app.selectbox(key=f"stats_filter_op_{index}").select(op)
    app.text_area(key=f"stats_filter_value_{index}").set_value(value)


def submit(app):
    app.button(key="stats_submit").click().run()
    assert not app.exception
    return app.session_state["_analysis_state"]


def four_age_metrics(app):
    set_metric(app, 0, "row_count", None, "rows")
    set_metric(app, 1, "count", "Age", "valid_age")
    set_metric(app, 2, "sum", "Age", "total_age")
    set_metric(app, 3, "mean", "Age", "mean_age")


def test_four_metrics_match_hand_calculation():
    app = uploaded_page()
    set_counts(app, metrics=4)
    four_age_metrics(app)
    session = submit(app)
    assert not app.error
    row = app.dataframe[2].value.to_dict("records")[0]
    assert row == pytest.approx({"rows": 8, "valid_age": 6, "total_age": 160, "mean_age": 80 / 3})
    data = session.current_result()["data"]
    assert data["session_id"] == session.session_id
    assert data["dataset_id"] == session.dataset.dataset_id
    assert data["run_id"] == session.run_id


def test_and_filters_in_list_and_alias_sort_are_submitted_as_typed_values():
    app = uploaded_page()
    set_counts(app, filters=2, sorts=1)
    app.multiselect(key="stats_groups").select("Sex")
    set_filter(app, 0, "Age", "ge", "30")
    set_filter(app, 1, "Sex", "in", "female\nmale")
    set_metric(app, 0, "mean", "Survived", "rate")
    app.text_input(key="stats_sort_field_0").set_value("rate")
    session = submit(app)
    assert not app.error
    assert app.dataframe[2].value.to_dict("records") == [
        {"Sex": "male", "rate": 0}, {"Sex": "female", "rate": 0.5},
    ]
    data = session.current_result()["data"]
    assert data["filtered_row_count"] == 3
    assert data["operations"]["filters"] == [
        {"column": "Age", "op": "ge", "value": 30.0},
        {"column": "Sex", "op": "in", "value": ["female", "male"]},
    ]


def test_empty_filter_succeeds_with_null_metrics_and_optional_empty_groups():
    app = uploaded_page()
    set_counts(app, filters=1, metrics=4)
    set_filter(app, 0, "Age", "gt", "100")
    four_age_metrics(app)
    session = submit(app)
    result = session.current_result()
    assert not app.error
    assert result["data"]["rows"] == [{"rows": 0, "valid_age": 0, "total_age": None, "mean_age": None}]
    assert result["data"]["filtered_row_count"] == 0
    assert "EMPTY_RESULT" in [item["code"] for item in result["warnings"]]
    assert any("EMPTY_RESULT" in item.value for item in app.warning)
    assert app.dataframe[2].value.iloc[0]["rows"] == 0
    app.multiselect(key="stats_groups").select("Sex")
    submit(app)
    assert not app.error
    assert app.dataframe[2].value.empty
    assert list(app.dataframe[2].value.columns) == ["Sex", "rows", "valid_age", "total_age", "mean_age"]


def test_missing_group_display_cannot_collide_with_real_category():
    app = uploaded_page(b"Group,Value\n<missing>,1\n,2\nz,\n")
    app.multiselect(key="stats_groups").select("Group")
    set_metric(app, 0, "sum", "Value", "total")
    session = submit(app)
    raw = session.current_result()["data"]["rows"]
    assert raw == [{"Group": "<missing>", "total": 1}, {"Group": "z", "total": None}, {"Group": None, "total": 2}]
    assert list(app.dataframe[2].value["Group"]) == ["<missing>", "z", "<missing> (null)"]
    assert any("NO_VALID_VALUES" in item.value for item in app.warning)


@pytest.mark.parametrize("invalid", [b"A,B\n", b"A,B\n1,2,3\n"])
def test_failed_upload_invalidates_statistics_and_clear_then_reupload_recovers(invalid):
    app = uploaded_page()
    session = submit(app)
    old_id = session.current_result_id
    app.file_uploader[0].upload("bad.csv", invalid, "text/csv").run()
    assert not app.exception
    assert not app.dataframe
    assert app.error
    session = app.session_state["_analysis_state"]
    assert session.dataset is None and session.run_id is None
    assert session.resolve_result(old_id)["error"]["code"] == "INVALID_RESULT_REFERENCE"
    app.file_uploader[0].clear().run()
    assert not app.error
    app.file_uploader[0].upload("sample.csv", (ROOT / "data/dev/eight_rows.csv").read_bytes(), "text/csv").run()
    assert not app.error and not app.exception
    assert len(app.dataframe) == 2
    assert app.session_state["_analysis_state"].current_result() is None


@pytest.mark.parametrize("case,code", [
    ("numeric_filter", "INVALID_FILTER_TYPE"),
    ("text_mean", "INCOMPATIBLE_AGGREGATION"),
    ("duplicate_alias", "INVALID_ARGUMENTS"),
    ("unknown_sort", "INVALID_SORT_FIELD"),
])
def test_invalid_submission_starts_new_run_and_does_not_show_old_result(case, code):
    app = uploaded_page()
    session = submit(app)
    old_run, old_id = session.run_id, session.current_result_id
    if case == "numeric_filter":
        set_counts(app, filters=1)
        set_filter(app, 0, "Age", "ge", "not a number")
    elif case == "text_mean":
        set_metric(app, 0, "mean", "Sex", "mean_sex")
    elif case == "duplicate_alias":
        set_counts(app, metrics=2)
        set_metric(app, 1, "row_count", None, "rows")
    else:
        set_counts(app, sorts=1)
        app.text_input(key="stats_sort_field_0").set_value("not_a_result_field")
    session = submit(app)
    assert code in app.error[0].value
    assert len(app.dataframe) == 2
    assert session.run_id != old_run and session.current_result() is None
    assert session.resolve_result(old_id)["error"]["code"] == "INVALID_RESULT_REFERENCE"


def test_two_actual_pages_keep_results_separate():
    first, second = uploaded_page(), uploaded_page()
    one, two = submit(first), submit(second)
    assert one.session_id != two.session_id
    assert one.current_result_id != two.current_result_id
    assert one.resolve_result(two.current_result_id)["error"]["code"] == "INVALID_RESULT_REFERENCE"
    assert two.resolve_result(one.current_result_id)["error"]["code"] == "INVALID_RESULT_REFERENCE"
    assert first.dataframe[2].value.to_dict("records") == [{"rows": 8}]
    assert second.dataframe[2].value.to_dict("records") == [{"rows": 8}]


def test_same_file_reupload_and_different_dataset_invalidate_old_results():
    app = uploaded_page()
    for name, content in [
        ("sample.csv", (ROOT / "data/dev/eight_rows.csv").read_bytes()),
        ("other.csv", b"City,Population\nLondon,10\nParis,20\n"),
    ]:
        session = submit(app)
        old_id, old_dataset = session.current_result_id, session.dataset.dataset_id
        app.file_uploader[0].upload(name, content, "text/csv").run()
        assert not app.exception and not app.error
        session = app.session_state["_analysis_state"]
        assert session.dataset.dataset_id != old_dataset
        assert session.run_id is None and session.current_result() is None
        assert session.resolve_result(old_id)["error"]["code"] == "INVALID_RESULT_REFERENCE"
        assert len(app.dataframe) == 2


def test_existing_p01_upload_survives_loading_the_p02_page():
    app = uploaded_page()
    previous = app.session_state["_analysis_state"].dataset
    # P01 kept its current Dataset under this key. Keep the actual uploader's
    # file_id/handled marker while simulating its pre-upgrade session state.
    del app.session_state["_analysis_state"]
    app.session_state["_dataset"] = previous
    app.run()
    assert not app.exception
    assert app.session_state["_analysis_state"].dataset.dataset_id == previous.dataset_id
    assert app.session_state["_analysis_state"].run_id is None
    assert len(app.dataframe) == 2
    assert submit(app).current_result()["data"]["rows"] == [{"rows": 8}]
