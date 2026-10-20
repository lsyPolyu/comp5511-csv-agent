"""Verify deterministic translations without a Streamlit session or model."""

import ast
from copy import deepcopy
from pathlib import Path
from string import Formatter

import pytest

from comp5511.i18n import (
    LANGUAGES, _ERROR_ZH, _OPTION_ZH, _TEXT_ZH,
    chart_defaults, message_text, option_label, text,
)

ROOT = Path(__file__).resolve().parents[1]


def placeholders(template):
    return [name for _, name, _, _ in Formatter().parse(template) if name is not None]


def test_all_registered_copy_preserves_english_and_translates_same_placeholders():
    assert LANGUAGES == ("en", "zh")
    values = {
        "dataset_id": "dataset-123", "result_id": "result-456", "run_id": "run-789",
        "chart_id": "chart-abc", "count": 8, "index": 2,
        "name": "原始列名", "missing_label": "<missing>",
    }
    for key, translated in _TEXT_ZH.items():
        assert placeholders(key) == placeholders(translated), key
        assert text(key, "en", **values) == key.format(**values)
        assert text(key, "zh", **values) == translated.format(**values)
        assert any("\u4e00" <= character <= "\u9fff" for character in translated), key


def test_dynamic_translation_preserves_identifiers_and_original_column_name():
    assert text("Dataset ID: {dataset_id}", "zh", dataset_id="原样-ID-123") == "数据集 ID：原样-ID-123"
    assert text("Filtered rows: {count}", "zh", count=8) == "筛选后行数：8"
    assert text("Missing group keys in {name!r} are displayed as {missing_label!r}.",
                "zh", name="Sex", missing_label="<missing>") == "分组列 'Sex' 中的缺失值显示为 '<missing>'。"


@pytest.mark.parametrize("value, expected", [
    ("mean", "平均值（mean）"), ("bar", "柱状图（bar）"),
    ("percent", "百分比（percent）"), (None, "无列（row_count）"),
])
def test_technical_display_labels_keep_english_tokens(value, expected):
    assert option_label(value, "zh") == expected
    assert option_label(value) == ("No column (row_count)" if value is None else value)


def test_all_technical_options_have_chinese_labels_and_keep_stable_english_values():
    expected = {"row_count", "count", "sum", "mean", "eq", "ne", "gt", "ge", "lt", "le", "in",
                "asc", "desc", "bar", "line", "default", "category", "numeric", "date",
                "number", "percent", "unknown", "fraction", "text"}
    assert set(_OPTION_ZH) == expected
    for value in expected:
        assert option_label(value) == value
        assert f"（{value}）" in option_label(value, "zh")


def test_unknown_text_and_options_fail_instead_of_silently_bypassing_translation():
    for language in LANGUAGES:
        with pytest.raises(KeyError):
            text("Unregistered interface copy", language)
        with pytest.raises(KeyError):
            option_label("CSV original column", language)
    with pytest.raises(KeyError):
        text("Dataset ID: {dataset_id}", "zh")


@pytest.mark.parametrize("function, args", [
    (text, ("Rows",)), (option_label, ("mean",)),
    (message_text, ({"code": "NO_DATASET", "message": "Upload first."},)),
    (chart_defaults, ()),
])
def test_unsupported_languages_fail_explicitly(function, args):
    with pytest.raises(ValueError, match="Unsupported interface language"):
        function(*args, language="fr")


def test_current_ui_translation_keys_are_all_registered():
    # Validate actual integration call sites, including new future UI copy.
    for filename in ("app.py", "comp5511/statistics_ui.py", "comp5511/chart_ui.py"):
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "text" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                assert node.args[0].value in _TEXT_ZH, (filename, node.lineno, node.args[0].value)


def test_every_current_error_and_warning_code_has_static_chinese_explanation():
    codes = set()
    for filename in ("datasets.py", "analysis.py", "state.py", "plotting.py", "statistics_ui.py"):
        tree = ast.parse((ROOT / "comp5511" / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("error_result", "DatasetError") and node.args
                    and isinstance(node.args[0], ast.Constant)):
                codes.add(node.args[0].value)
            if isinstance(node, ast.Dict):
                codes.update(value.value for key, value in zip(node.keys, node.values)
                             if isinstance(key, ast.Constant) and key.value == "code"
                             and isinstance(value, ast.Constant) and isinstance(value.value, str))
    assert codes
    assert codes <= _ERROR_ZH.keys()
    for code in codes:
        message = {"code": code, "message": "Original English detail: Sex; 0.75; result-123."}
        original = deepcopy(message)
        assert message_text(message) == f"{code}: {message['message']}"
        chinese = message_text(message, "zh")
        assert chinese.startswith(f"{code}: {_ERROR_ZH[code]}")
        assert message["message"] in chinese
        assert message == original


def test_unknown_error_code_has_chinese_fallback_and_retains_original_detail():
    message = {"code": "NEW_UNRECOGNIZED_ERROR", "message": "Unexpected problem in alias 原样."}
    assert message_text(message) == "NEW_UNRECOGNIZED_ERROR: Unexpected problem in alias 原样."
    chinese = message_text(message, "zh")
    assert chinese.startswith("NEW_UNRECOGNIZED_ERROR: 操作未完成")
    assert chinese.endswith(message["message"])


def test_chart_defaults_are_language_specific_fresh_and_percent_label_keeps_marker():
    assert chart_defaults() == {"chart_title": "Analysis result", "chart_x_label": "X value", "chart_y_label": "Value"}
    assert chart_defaults("zh") == {"chart_title": "统计结果", "chart_x_label": "X 值", "chart_y_label": "数值"}
    defaults = chart_defaults("zh")
    defaults["chart_title"] = "User edited"
    assert chart_defaults("zh")["chart_title"] == "统计结果"
    assert text("Value (%)", "zh") == "数值 (%)"
