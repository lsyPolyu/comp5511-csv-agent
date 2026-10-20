"""Exercise the real page and uploader callbacks through Streamlit AppTest.

AppTest simulates widget uploads; it does not check a browser file picker or layout.
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"
SAMPLE = (
    b"Sex,Survived,Age\nfemale,1,20\nfemale,1,30\nfemale,1,\nfemale,0,40\n"
    b"male,1,10\nmale,0,20\nmale,0,\nmale,0,40\n"
)


def page():
    return AppTest.from_file(str(APP), default_timeout=10).run()


def test_initial_page_needs_no_key_or_model(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app = page()
    assert not app.exception
    assert app.title[0].value == "CSV Dataset Inspector"
    assert "No API key or model is used" in app.caption[0].value
    assert "Select a CSV" in app.info[0].value
    assert not app.dataframe


def test_page_displays_real_inspection_and_preserves_context_on_rerun():
    app = page()
    app.file_uploader[0].upload("sample.csv", SAMPLE, "text/csv").run()
    assert not app.exception
    assert [(metric.label, metric.value) for metric in app.metric] == [
        ("Rows", "8"), ("Columns", "3"),
    ]
    assert len(app.dataframe[0].value) == 5
    summary = app.dataframe[1].value.set_index("Column")
    assert summary.loc["Age", "Missing count"] == 2
    assert summary.loc["Age", "Missing ratio"] == 0.25
    dataset_id = app.caption[1].value
    app.run()
    assert not app.exception
    assert app.caption[1].value == dataset_id


@pytest.mark.parametrize("content, filename, error_code", [
    (b"", "empty.csv", "EMPTY_DATASET"),
    (b"A,B\n", "header.csv", "EMPTY_DATASET"),
    (b"A\n\xff\n", "encoding.csv", "CSV_PARSE_ERROR"),
    (b"A,B\n1,2,3\n", "width.csv", "CSV_PARSE_ERROR"),
    (b"A,A\n1,2\n", "duplicate.csv", "INVALID_HEADER"),
    (b",B\n1,2\n", "empty-header.csv", "INVALID_HEADER"),
    (SAMPLE, "sample.txt", "UNSUPPORTED_INPUT"),
])
def test_failed_replacement_removes_old_preview_and_clearing_removes_error(
    content, filename, error_code,
):
    app = page()
    app.file_uploader[0].upload("sample.csv", SAMPLE, "text/csv").run()
    assert app.dataframe
    app.file_uploader[0].upload(filename, content, "text/csv").run()
    assert not app.exception
    assert error_code in app.error[0].value
    assert "No current dataset" in app.info[0].value
    assert not app.metric
    assert not app.dataframe
    app.file_uploader[0].clear().run()
    assert not app.exception
    assert not app.error
    assert not app.dataframe


def test_successful_replacement_and_separate_sessions_use_new_contexts():
    first = page()
    first.file_uploader[0].upload("sample.csv", SAMPLE, "text/csv").run()
    first_id = first.caption[1].value
    separate = page()
    assert not separate.dataframe
    separate.file_uploader[0].upload("sample.csv", SAMPLE, "text/csv").run()
    assert separate.caption[1].value != first_id
    first.file_uploader[0].upload(
        "cities.csv", b"City,Population\nLondon,10\n", "text/csv",
    ).run()
    assert not first.exception
    assert first.caption[1].value != first_id
    assert first.metric[0].value == "1"
    assert list(first.dataframe[0].value.columns) == ["City", "Population"]


def test_explicit_reupload_of_same_file_creates_new_dataset():
    app = page()
    app.file_uploader[0].upload("sample.csv", SAMPLE, "text/csv").run()
    dataset_id = app.caption[1].value
    app.file_uploader[0].upload("sample.csv", SAMPLE, "text/csv").run()
    assert not app.exception
    assert app.caption[1].value != dataset_id
