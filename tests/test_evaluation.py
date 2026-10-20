"""The agent's tools and the independent Pandas references must agree on every
task (oracle calls), faults must trigger, and the scorer must reject wrong values."""

import copy
import json

from comp5511.controller import AgentConfig, run_agent
from comp5511.datasets import load_csv
from comp5511.llm import FakeLLM
from comp5511.state import AnalysisSession
from evaluation.faults import Injector, load_faults
from evaluation.references import DATA_FILES, all_references, load_tasks
from evaluation.scoring import score_run, snapshot

WINNERS = {"T11": "Female", "T12": "First class", "T13": "Female", "T14": "Male", "B11": "Fall",
           "B12": "2012", "B13": "Friday", "B14": "2012", "D05": "Female"}


def _oracle(task):
    spec, metric = task["spec"], task["spec"]["metric"]
    call = {"operation": metric["operation"], "alias": "value"}
    if metric["column"]:
        call["column"] = metric["column"]
    steps = [[("aggregate_data", {"filters": spec["filters"], "group_by": spec["group_by"], "metrics": [call]})]]

    def last_result(messages):
        for message in reversed(messages):
            if message["role"] == "tool" and json.loads(message["content"]).get("result_id"):
                return json.loads(message["content"])["result_id"]

    if task.get("chart"):
        steps.append(lambda messages: [("plot_result", {
            "result_id": last_result(messages), "chart_type": task["chart"], "x": spec["group_by"][0],
            "y": "value", "title": "t", "x_label": "x", "y_label": "y"})])
    steps.append(f"{WINNERS.get(task['task_id'], 'Done')}: see the result.")
    return FakeLLM(steps)


def _run(task, mode="proposed", injector=None):
    session = AnalysisSession()
    session.replace_dataset(load_csv(DATA_FILES[task["dataset"]].read_bytes(), "data.csv"))
    run = run_agent(task["question"], session, _oracle(task), AgentConfig(mode=mode), injector=injector)
    return {"status": run.status, "answer": run.answer, **snapshot(session, run)}, run


def test_tools_and_references_agree_on_all_tasks():
    references = all_references()
    tasks = load_tasks()
    assert len([t for t in tasks if t["split"] == "formal"]) == 40
    assert len([t for t in tasks if t["split"] == "dev"]) == 10
    for task in tasks:
        record, _ = _run(task)
        assert score_run(task, references[task["task_id"]], record)["success"], task["task_id"]


def test_scorer_rejects_a_wrong_value():
    task = next(t for t in load_tasks() if t["task_id"] == "T11")
    reference = copy.deepcopy(all_references()["T11"])
    reference["rows"]['["female"]'] = 0.25
    record, _ = _run(task)
    assert not score_run(task, reference, record)["success"]


def test_every_fault_triggers_once_and_baseline_does_not_recover():
    tasks = {t["task_id"]: t for t in load_tasks()}
    for fault in load_faults():
        injector = Injector(fault)
        record, run = _run(tasks[fault["task_id"]], mode="baseline", injector=injector)
        assert injector.triggered, fault["fault_id"]
        assert not score_run(tasks[fault["task_id"]], all_references()[fault["task_id"]], record)["success"]
