"""P02/P03 server lifecycle, provenance, and reference isolation checks."""

from uuid import UUID, uuid4

import pytest

from comp5511.datasets import DatasetError, load_csv
from comp5511.state import AnalysisSession


def dataset():
    return load_csv(b"Value\n1\n2\n", "example.csv")


def success(session):
    """A hand-authored protocol fixture, not an aggregation oracle."""
    metrics = [{"operation": "row_count", "column": None, "alias": "Rows"}]
    return {
        "success": True, "error": None, "warnings": [],
        "data": {
            "result_id": str(uuid4()), "session_id": session.session_id,
            "dataset_id": session.dataset.dataset_id, "run_id": session.run_id,
            "filtered_row_count": 2, "group_by": [], "metrics": metrics,
            "fields": [{"name": "Rows", "logical_type": "numeric", "role": "metric"}],
            "rows": [{"Rows": 2}],
            "operations": {"filters": [], "group_by": [], "metrics": metrics, "sort_by": []},
        },
    }


def active_session():
    session = AnalysisSession()
    session.replace_dataset(dataset())
    session.begin_run()
    return session


def test_session_generates_its_own_unique_id():
    first, second = AnalysisSession(), AnalysisSession()
    assert str(UUID(first.session_id)) == first.session_id
    assert first.session_id != second.session_id
    assert first.dataset is None
    assert first.run_id is None
    assert first.current_result_id is None


def test_run_requires_dataset_and_is_explicitly_created():
    session = AnalysisSession()
    with pytest.raises(ValueError, match="Upload a valid CSV"):
        session.begin_run()
    source = dataset()
    session.replace_dataset(source)
    assert session.dataset is source
    assert session.run_id is None
    first_run = session.begin_run()
    assert str(UUID(first_run)) == first_run
    assert session.begin_run() != first_run


def test_replacement_and_clear_invalidate_the_current_run():
    session = AnalysisSession()
    session.replace_dataset(dataset())
    session.begin_run()
    replacement = dataset()
    session.replace_dataset(replacement)
    assert session.dataset is replacement
    assert session.run_id is None
    session.begin_run()
    session.clear_dataset()
    assert session.dataset is None
    assert session.run_id is None
    assert session.current_result_id is None


def test_success_is_published_and_reads_do_not_start_a_run():
    session = active_session()
    run_id = session.run_id
    result = success(session)
    assert session.publish_result(result) == result
    assert session.current_result_id == result["data"]["result_id"]
    assert session.current_result() == result
    assert session.resolve_result(result["data"]["result_id"]) == result
    assert session.run_id == run_id


def test_publishing_and_resolving_make_independent_copies():
    session = active_session()
    result = success(session)
    published = session.publish_result(result)
    result["data"]["rows"][0]["Rows"] = -1
    published["data"]["rows"][0]["Rows"] = -2
    current = session.current_result()
    assert current["data"]["rows"] == [{"Rows": 2}]
    current["data"]["rows"][0]["Rows"] = -3
    assert session.current_result()["data"]["rows"] == [{"Rows": 2}]


def test_multiple_successes_are_resolvable_and_failure_does_not_replace_them():
    session = active_session()
    first, second = success(session), success(session)
    session.publish_result(first)
    session.publish_result(second)
    failure = {
        "success": False, "data": None, "warnings": [],
        "error": {"code": "UNKNOWN_COLUMN", "field": "column", "message": "Unknown column.", "error_stage": "dataset_validation"},
    }
    assert session.publish_result(failure) == failure
    assert session.current_result() == second
    assert session.resolve_result(first["data"]["result_id"]) == first


def assert_invalid(response):
    assert response["success"] is False
    assert response["data"] is None
    assert response["error"]["code"] == "INVALID_RESULT_REFERENCE"
    assert response["error"]["error_stage"] == "dataset_validation"


def test_cross_session_read_and_publish_are_rejected_without_changing_own_result():
    owner, other = active_session(), active_session()
    owned, own = success(owner), success(other)
    owner.publish_result(owned)
    other.publish_result(own)
    assert_invalid(other.resolve_result(owned["data"]["result_id"]))
    assert_invalid(other.publish_result(owned))
    assert other.current_result() == own
    assert owner.current_result() == owned


@pytest.mark.parametrize("transition", ["new_run", "replacement", "same_file", "clear", "failed_load"])
def test_stale_reads_and_late_publications_are_rejected(transition):
    session = active_session()
    previous = success(session)
    previous_dataset_id = session.dataset.dataset_id
    session.publish_result(previous)
    if transition == "new_run":
        session.begin_run()
    elif transition == "replacement":
        session.replace_dataset(load_csv(b"Other\n3\n", "other.csv"))
        session.begin_run()
    elif transition == "same_file":
        session.replace_dataset(dataset())
        assert session.dataset.dataset_id != previous_dataset_id
        session.begin_run()
    elif transition == "clear":
        session.clear_dataset()
    else:
        session.clear_dataset()
        with pytest.raises(DatasetError, match="header alone"):
            session.replace_dataset(load_csv(b"Value\n", "broken.csv"))
        assert session.dataset is None
    assert session.current_result() is None
    assert_invalid(session.resolve_result(previous["data"]["result_id"]))
    assert_invalid(session.publish_result(previous))
    assert session.current_result_id is None


@pytest.mark.parametrize("field", ["session_id", "dataset_id", "run_id"])
def test_forged_context_is_rejected(field):
    session = active_session()
    forged = success(session)
    forged["data"][field] = "unrelated-context"
    assert_invalid(session.publish_result(forged))
    assert session.current_result() is None


@pytest.mark.parametrize("missing", ["result_id", "filtered_row_count", "metrics", "fields", "rows", "operations"])
def test_incomplete_success_cannot_be_published(missing):
    session = active_session()
    result = success(session)
    del result["data"][missing]
    assert_invalid(session.publish_result(result))
    assert session.current_result_id is None


def test_unknown_reference_is_rejected_without_starting_a_run():
    session = AnalysisSession()
    assert session.current_result() is None
    assert_invalid(session.resolve_result("unknown-result"))
    assert_invalid(session.resolve_result(None))
    assert session.run_id is None


def test_duplicate_result_id_cannot_overwrite_a_registered_success():
    session = active_session()
    result = success(session)
    session.publish_result(result)
    result["data"]["rows"] = [{"Rows": -1}]
    assert_invalid(session.publish_result(result))
    assert session.current_result()["data"]["rows"] == [{"Rows": 2}]


@pytest.mark.parametrize("damage", ["missing_operation_metadata", "missing_field_type", "missing_row_value", "infinite_row_value"])
def test_partial_or_nonfinite_success_is_not_a_registered_result(damage):
    session = active_session()
    result = success(session)
    if damage == "missing_operation_metadata":
        result["data"]["operations"] = {}
    elif damage == "missing_field_type":
        del result["data"]["fields"][0]["logical_type"]
    elif damage == "missing_row_value":
        result["data"]["rows"] = [{}]
    else:
        result["data"]["rows"][0]["Rows"] = float("inf")
    assert_invalid(session.publish_result(result))
    assert session.current_result() is None


def test_real_aggregation_registers_with_server_context_and_failure_preserves_it():
    from comp5511.analysis import aggregate_data

    session = active_session()
    result = aggregate_data(
        session.dataset,
        {"metrics": [{"operation": "sum", "column": "Value", "alias": "Total"}]},
        session_id=session.session_id, run_id=session.run_id,
    )
    assert result["success"] is True
    assert result["data"]["rows"] == [{"Total": 3}]
    assert session.publish_result(result) == result
    assert session.current_result() == result
    failed = aggregate_data(
        session.dataset,
        {"metrics": [{"operation": "sum", "column": "Unknown", "alias": "Total"}]},
        session_id=session.session_id, run_id=session.run_id,
    )
    assert failed["success"] is False
    assert session.publish_result(failed) == failed
    assert session.current_result() == result
    assert session.dataset.raw_rows == (("1",), ("2",))


PNG_BYTES = b"\x89PNG\r\n\x1a\nhand-authored-test-artifact"


def chart_success(session, result):
    """A protocol fixture with independently specified underlying source values."""
    chart_id = str(uuid4())
    return {
        "success": True, "error": None, "warnings": [],
        "data": {
            "chart_id": chart_id, "result_id": result["data"]["result_id"],
            "session_id": session.session_id, "dataset_id": session.dataset.dataset_id,
            "run_id": session.run_id, "chart_type": "bar", "x": "Rows", "y": "Rows",
            "title": "Total rows", "x_label": "Rows", "y_label": "Rows",
            "format": {"x_kind": "category", "date_format": None,
                       "y_format": "number", "decimal_places": 2, "unit": "unknown"},
            "plot_data": [{"source_index": 0, "x": 2, "y": 2, "x_sort_key": None,
                           "display_x": "2", "display_y": "2.00"}],
            "artifact": {"format": "png", "mime_type": "image/png",
                         "filename": chart_id + ".png", "size_bytes": len(PNG_BYTES)},
        },
    }


def chart_session():
    session = active_session()
    result = session.publish_result(success(session))
    return session, result, chart_success(session, result)


def test_chart_publication_is_detached_and_does_not_start_a_run():
    session, result, chart = chart_session()
    run_id = session.run_id
    assert session.publish_chart(chart, PNG_BYTES) == chart
    assert session.current_chart() == chart
    assert session.chart_bytes(chart["data"]["chart_id"]) == PNG_BYTES
    assert session.current_result() == result
    assert session.run_id == run_id
    chart["data"]["title"] = "Changed caller data"
    resolved = session.current_chart()
    assert resolved["data"]["title"] == "Total rows"
    resolved["data"]["plot_data"][0]["y"] = 999
    assert session.current_chart()["data"]["plot_data"][0]["y"] == 2


def assert_invalid_chart(response):
    assert response["success"] is False
    assert response["data"] is None
    assert response["error"]["code"] == "INVALID_CHART_REFERENCE"
    assert response["error"]["error_stage"] == "dataset_validation"


def test_replacing_chart_releases_the_old_artifact_and_failed_plot_preserves_current():
    session, result, first = chart_session()
    session.publish_chart(first, PNG_BYTES)
    second = chart_success(session, result)
    assert session.publish_chart(second, PNG_BYTES) == second
    old_id = first["data"]["chart_id"]
    assert_invalid_chart(session.resolve_chart(old_id))
    assert session.chart_bytes(old_id) is None
    assert session._chart[0] == second
    assert_invalid_chart(session.publish_chart(second, PNG_BYTES))
    failure = {"success": False, "data": None, "warnings": [],
               "error": {"code": "NO_PLOTTABLE_DATA", "field": "y", "message": "No valid values.",
                         "error_stage": "dataset_validation"}}
    assert session.publish_chart(failure, b"") == failure
    assert session.current_chart() == second


@pytest.mark.parametrize("damage", [
    "missing_id", "missing_format", "missing_format_field", "missing_rows", "missing_source_index",
    "bad_source_index", "duplicate_source_index", "unknown_x", "forged_value", "nonfinite_value",
    "bad_chart_type", "bad_png", "mutable_png", "wrong_size", "wrong_filename", "missing_error",
])
def test_incomplete_or_forged_chart_never_replaces_the_current_success(damage):
    session, result, original = chart_session()
    session.publish_chart(original, PNG_BYTES)
    chart, png = chart_success(session, result), PNG_BYTES
    if damage == "missing_id":
        del chart["data"]["chart_id"]
    elif damage == "missing_format":
        del chart["data"]["format"]
    elif damage == "missing_format_field":
        del chart["data"]["format"]["unit"]
    elif damage == "missing_rows":
        chart["data"]["plot_data"] = []
    elif damage == "missing_source_index":
        del chart["data"]["plot_data"][0]["source_index"]
    elif damage == "bad_source_index":
        chart["data"]["plot_data"][0]["source_index"] = -1
    elif damage == "duplicate_source_index":
        chart["data"]["plot_data"] *= 2
    elif damage == "unknown_x":
        chart["data"]["x"] = "Invented"
    elif damage == "forged_value":
        chart["data"]["plot_data"][0]["y"] = 10
    elif damage == "nonfinite_value":
        chart["data"]["plot_data"][0]["y"] = float("inf")
    elif damage == "bad_chart_type":
        chart["data"]["chart_type"] = "pie"
    elif damage == "bad_png":
        png = b"not-a-png"
        chart["data"]["artifact"]["size_bytes"] = len(png)
    elif damage == "mutable_png":
        png = bytearray(PNG_BYTES)
    elif damage == "wrong_size":
        chart["data"]["artifact"]["size_bytes"] += 1
    elif damage == "wrong_filename":
        chart["data"]["artifact"]["filename"] = "other.png"
    else:
        del chart["error"]
    assert_invalid_chart(session.publish_chart(chart, png))
    assert session.current_chart() == original


@pytest.mark.parametrize("transition", ["new_run", "replacement", "same_file", "clear", "failed_load", "new_result"])
def test_chart_is_discarded_on_each_context_or_current_result_change(transition):
    session, _, chart = chart_session()
    session.publish_chart(chart, PNG_BYTES)
    old_id = chart["data"]["chart_id"]
    if transition == "new_run":
        session.begin_run()
    elif transition == "replacement":
        session.replace_dataset(load_csv(b"Other\n3\n", "other.csv"))
    elif transition == "same_file":
        session.replace_dataset(dataset())
    elif transition == "clear":
        session.clear_dataset()
    elif transition == "failed_load":
        session.clear_dataset()
        with pytest.raises(DatasetError):
            load_csv(b"Value\n", "broken.csv")
    else:
        session.publish_result(success(session))
    assert session.current_chart() is None
    assert session.current_chart_id is None
    assert session._chart is None
    assert session.chart_bytes(old_id) is None
    assert_invalid_chart(session.resolve_chart(old_id))
    if transition != "new_result":
        assert_invalid(session.publish_chart(chart, PNG_BYTES))


@pytest.mark.parametrize("field", ["session_id", "dataset_id", "run_id", "result_id"])
def test_foreign_or_unknown_chart_sources_cannot_replace_own_chart(field):
    session, result, own = chart_session()
    session.publish_chart(own, PNG_BYTES)
    forged = chart_success(session, result)
    forged["data"][field] = "unrelated-source"
    assert_invalid(session.publish_chart(forged, PNG_BYTES))
    assert session.current_chart() == own


def test_cross_session_chart_reference_and_publication_are_rejected():
    owner, _, chart = chart_session()
    other, _, own = chart_session()
    owner.publish_chart(chart, PNG_BYTES)
    other.publish_chart(own, PNG_BYTES)
    assert_invalid_chart(other.resolve_chart(chart["data"]["chart_id"]))
    assert other.chart_bytes(chart["data"]["chart_id"]) is None
    assert_invalid(other.publish_chart(chart, PNG_BYTES))
    assert other.current_chart() == own


@pytest.mark.parametrize("damage", ["context", "source"])
@pytest.mark.parametrize("reader", ["current", "resolve", "bytes"])
def test_chart_reads_recheck_context_and_release_invalid_resources(damage, reader):
    session, result, chart = chart_session()
    session.publish_chart(chart, PNG_BYTES)
    if damage == "context":
        session.run_id = str(uuid4())
    else:
        session._results.pop(result["data"]["result_id"])
    if reader == "current":
        assert session.current_chart() is None
    elif reader == "resolve":
        assert_invalid_chart(session.resolve_chart(chart["data"]["chart_id"]))
    else:
        assert session.chart_bytes(chart["data"]["chart_id"]) is None
    assert session.current_chart_id is None
    assert session._chart is None


def test_old_live_session_without_chart_fields_retains_statistics_when_upgraded():
    session, result, chart = chart_session()
    del session.current_chart_id
    del session._chart
    assert session.current_chart() is None
    assert_invalid_chart(session.resolve_chart("unknown"))
    assert session.chart_bytes("unknown") is None
    assert session.current_result() == result
    assert session.publish_chart(chart, PNG_BYTES) == chart


def test_declared_source_metadata_must_match_the_registered_result():
    session, result, chart = chart_session()
    chart["data"]["source"] = {
        key: result["data"][key] for key in ("fields", "operations", "filtered_row_count")
    }
    assert session.publish_chart(chart, PNG_BYTES) == chart
    forged = chart_success(session, result)
    forged["data"]["source"] = {"fields": [], "operations": {}, "filtered_row_count": 200}
    assert_invalid_chart(session.publish_chart(forged, PNG_BYTES))
    assert session.current_chart() == chart
