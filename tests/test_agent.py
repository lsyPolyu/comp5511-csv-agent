"""Offline tests for tools, validation and the agent loop (FakeLLM, no network)."""

import json
from pathlib import Path

from comp5511.controller import AgentConfig, run_agent
from comp5511.datasets import load_csv
from comp5511.llm import FakeLLM, LLMError
from comp5511.state import AnalysisSession
from comp5511.tools import TOOL_SPECS, dispatch
from comp5511.validation import validate

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "dev" / "eight_rows.csv"

GOOD_AGG = {"group_by": ["Sex"], "metrics": [{"operation": "mean", "column": "Survived", "alias": "rate"}]}
BAD_AGG = {"group_by": ["gender"], "metrics": [{"operation": "mean", "column": "Survived", "alias": "rate"}]}


def _session():
    session = AnalysisSession()
    session.replace_dataset(load_csv(FIXTURE.read_bytes(), "eight_rows.csv"))
    session.begin_run()
    return session


def _plot(result_id):
    return {"result_id": result_id, "chart_type": "bar", "x": "Sex", "y": "rate",
            "title": "Survival rate by sex", "x_label": "Sex", "y_label": "Survival rate"}


def _plot_from_last_result(messages):
    for message in reversed(messages):
        if message["role"] == "tool":
            content = json.loads(message["content"])
            if content.get("result_id"):
                return [("plot_result", _plot(content["result_id"]))]
    raise AssertionError("no result_id in messages")


# ---------- tools ----------

def test_tool_specs_are_plain_json_schema():
    names = [spec["function"]["name"] for spec in TOOL_SPECS]
    assert names == ["inspect_dataset", "aggregate_data", "plot_result"]
    text = json.dumps(TOOL_SPECS)
    assert "$ref" not in text and "$defs" not in text


def test_dispatch_matches_hand_calculation():
    session = _session()
    result = dispatch("aggregate_data", json.dumps(GOOD_AGG), session)
    assert result["success"]
    rows = {row["Sex"]: row["rate"] for row in result["data"]["rows"]}
    assert rows == {"female": 0.75, "male": 0.25}


def test_dispatch_structured_errors():
    session = _session()
    assert dispatch("drop_table", "{}", session)["error"]["code"] == "UNKNOWN_TOOL"
    assert dispatch("aggregate_data", "{not json", session)["error"]["code"] == "INVALID_JSON"
    extra = dict(GOOD_AGG, limit=5)
    assert dispatch("aggregate_data", json.dumps(extra), session)["error"]["code"] == "INVALID_ARGUMENTS"
    assert dispatch("aggregate_data", json.dumps(BAD_AGG), session)["error"]["code"] == "INVALID_COLUMN"


# ---------- validation ----------

def test_validator_suggests_real_column_without_changing_call():
    session = _session()
    issue = validate("aggregate_data", json.dumps(BAD_AGG), session)
    assert issue["code"] == "UNKNOWN_COLUMN" and issue["requested"] == "gender"
    assert issue["available_columns"] == ["Sex", "Survived", "Age"]
    assert validate("aggregate_data", json.dumps(GOOD_AGG), session) is None


def test_validator_type_category_and_result_checks():
    session = _session()
    mean_text = {"metrics": [{"operation": "mean", "column": "Sex", "alias": "m"}]}
    assert validate("aggregate_data", json.dumps(mean_text), session)["code"] == "INCOMPATIBLE_OPERATION"
    male = dict(GOOD_AGG, filters=[{"column": "Sex", "op": "eq", "value": "Male"}])
    issue = validate("aggregate_data", json.dumps(male), session)
    assert issue["code"] == "UNKNOWN_CATEGORY" and issue["close_matches"][0] == "male"
    as_text = dict(GOOD_AGG, filters=[{"column": "Age", "op": "gt", "value": "30"}])
    assert validate("aggregate_data", json.dumps(as_text), session)["code"] == "FILTER_TYPE_MISMATCH"
    assert validate("plot_result", json.dumps(_plot("nope")), session)["code"] == "UNKNOWN_RESULT"


def test_legal_empty_filter_is_not_an_error():
    session = _session()
    empty = dict(GOOD_AGG, filters=[{"column": "Age", "op": "gt", "value": 100}])
    assert validate("aggregate_data", json.dumps(empty), session) is None


# ---------- controller ----------

def test_normal_path_produces_answer_table_and_chart():
    llm = FakeLLM([[("aggregate_data", GOOD_AGG)], _plot_from_last_result, "Female 0.75, male 0.25."])
    run = run_agent("Survival rate by sex as a bar chart?", _session(), llm, AgentConfig(mode="baseline"))
    assert run.status == "completed" and run.tool_calls == 2 and run.repairs == 0
    assert len(run.result_ids) == 1 and run.chart_id


def test_baseline_stops_at_first_failure_and_skips_rest_of_batch():
    llm = FakeLLM([[("aggregate_data", BAD_AGG), ("inspect_dataset", {})], "should not be used"])
    run = run_agent("q", _session(), llm, AgentConfig(mode="baseline"))
    assert run.status == "tool_error" and run.tool_calls == 1 and run.model_requests == 1
    assert run.steps[-1]["skipped"] == "previous_call_failed"


def test_proposed_feedback_lets_model_repair():
    def repair(messages):
        feedback = json.loads(messages[-1]["content"])
        assert feedback["error"]["code"] == "UNKNOWN_COLUMN"
        assert "Sex" in feedback["error"]["close_matches"] or "Sex" in feedback["error"]["available_columns"]
        return [("aggregate_data", GOOD_AGG)]

    llm = FakeLLM([[("aggregate_data", BAD_AGG)], repair, "Female 0.75, male 0.25."])
    run = run_agent("q", _session(), llm, AgentConfig(mode="proposed"))
    assert run.status == "completed" and run.tool_calls == 2 and run.repairs == 1
    assert run.first_error["code"] == "UNKNOWN_COLUMN"


def test_raw_retry_sees_only_raw_error():
    def repair(messages):
        feedback = json.loads(messages[-1]["content"])
        assert "available_columns" not in feedback["error"]
        return [("aggregate_data", GOOD_AGG)]

    llm = FakeLLM([[("aggregate_data", BAD_AGG)], repair, "done"])
    run = run_agent("q", _session(), llm, AgentConfig(mode="raw_retry"))
    assert run.status == "completed" and run.repairs == 1


def test_repairs_are_bounded_and_inspect_only_round_counts():
    llm = FakeLLM([[("aggregate_data", BAD_AGG)], [("inspect_dataset", {}), ("aggregate_data", BAD_AGG)],
                   [("aggregate_data", BAD_AGG)], "never"])
    run = run_agent("q", _session(), llm, AgentConfig(mode="proposed"))
    assert run.status == "repair_exhausted" and run.repairs == 2 and run.tool_calls == 4


def test_text_after_error_is_unresolved():
    llm = FakeLLM([[("aggregate_data", BAD_AGG)], "Which column do you mean?"])
    run = run_agent("q", _session(), llm, AgentConfig(mode="proposed"))
    assert run.status == "unresolved" and run.repairs == 1


def test_tool_budget_of_eight():
    llm = FakeLLM([[("inspect_dataset", {})] * 5, [("inspect_dataset", {})] * 5, "closing answer"])
    run = run_agent("q", _session(), llm, AgentConfig(mode="proposed"))
    assert run.tool_calls == 8 and run.status == "budget_exhausted"
    assert run.answer == "closing answer" and run.steps[-2]["skipped"] == "tool_budget_exhausted"


def test_api_error_is_not_a_tool_error():
    llm = FakeLLM([LLMError("rate_limit", "slow down")])
    run = run_agent("q", _session(), llm, AgentConfig(mode="proposed"))
    assert run.status == "api_error" and run.tool_calls == 0


def test_injector_replaces_a_field_and_is_recorded():
    def injector(name, raw):
        if name != "aggregate_data":
            return raw, None
        args = json.loads(raw)
        args["group_by"] = ["gender"]
        return json.dumps(args), {"field": "group_by.0", "before": "Sex", "after": "gender"}

    llm = FakeLLM([[("aggregate_data", GOOD_AGG)], "x"])
    run = run_agent("q", _session(), llm, AgentConfig(mode="baseline"), injector=injector)
    assert run.status == "tool_error" and run.steps[1]["injected"]["after"] == "gender"
