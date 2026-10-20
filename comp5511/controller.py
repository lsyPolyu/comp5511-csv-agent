"""The agent loop. One controller, three modes that differ only after a tool fails.

baseline   - the first failed tool call ends the task (status tool_error).
raw_retry  - the error code and raw message go back to the model; up to 2 repair rounds.
proposed   - dataset-aware validation runs before each call; structured feedback goes
             back to the model; up to 2 repair rounds.

Counting rules (fixed before the experiments):
T  every attempted tool call counts, success or failure; at most 8 per task.
   Within one model response calls run in order; after the first failure the
   rest are answered with "skipped" and do not count.
R  the first model response after a failed call is one repair round, whatever
   it does. After 2 rounds, another failure ends the task (repair_exhausted).
When T reaches 8 the model gets one last request without tools to write its answer.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

from comp5511.llm import LLMError
from comp5511.state import AnalysisSession
from comp5511.tools import TOOL_NAMES, TOOL_SPECS, dataset_summary, dispatch, result_for_model
from comp5511.validation import feedback_envelope, validate

MODES = ("baseline", "raw_retry", "proposed")

SYSTEM_PROMPT = (
    "You are a data analysis assistant for one uploaded CSV file. Answer the user's question "
    "using only the provided tools: inspect_dataset, aggregate_data and plot_result.\n"
    "- Use exact column names and category values as they appear in the dataset.\n"
    "- Every number in your answer must come from a tool result; never estimate or compute numbers yourself.\n"
    "- A rate of a 0/1 column is the mean of that column.\n"
    "- If a chart is requested, first compute the values with aggregate_data, then call plot_result "
    "with that result_id.\n"
    "- When finished, reply with a short English answer that states the key numbers and the "
    "result_id(s) you used.\n"
    "- If you cannot answer, say what is missing or ask the user a clarifying question."
)


@dataclass
class AgentConfig:
    mode: str = "proposed"
    max_tool_calls: int = 8
    max_repairs: int = 2
    max_model_requests: int = 12
    task_timeout_s: float = 180.0

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")


@dataclass
class RunResult:
    mode: str
    status: str = "running"
    answer: str | None = None
    result_ids: list = field(default_factory=list)
    chart_id: str | None = None
    tool_calls: int = 0           # T
    repairs: int = 0              # R
    model_requests: int = 0
    network_retries: int = 0
    prompt_tokens: int | None = 0
    completion_tokens: int | None = 0
    latency_s: float = 0.0
    first_error: dict | None = None
    error_message: str | None = None
    steps: list = field(default_factory=list)
    model: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _add_usage(result: RunResult, usage: dict | None) -> None:
    if usage is None:  # unknown usage stays unknown, never 0
        result.prompt_tokens = result.completion_tokens = None
        return
    if result.prompt_tokens is not None:
        result.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        result.completion_tokens += int(usage.get("completion_tokens") or 0)


def build_messages(question: str, session: AnalysisSession, data_notes: str = "") -> list[dict]:
    summary = dataset_summary(session)
    user = f"Question: {question}\n\nDataset summary (from inspect_dataset):\n{json.dumps(summary, default=str)}"
    if data_notes:
        user += f"\n\nColumn notes:\n{data_notes}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _execute(name: str, raw_arguments: str, session: AnalysisSession, mode: str) -> dict:
    if mode == "proposed":
        if name not in TOOL_NAMES:
            return feedback_envelope({"code": "UNKNOWN_TOOL", "field": "name", "requested": name,
                                      "message": f"Unknown tool '{name}'.", "available_tools": list(TOOL_NAMES),
                                      "error_stage": "dataset_validation"})
        issue = validate(name, raw_arguments, session)
        if issue:
            return feedback_envelope(issue)
    return dispatch(name, raw_arguments, session)


def run_agent(question: str, session: AnalysisSession, llm, config: AgentConfig | None = None,
              data_notes: str = "", injector=None) -> RunResult:
    """Answer one question about session.dataset. injector(name, raw_args) -> (raw_args, info|None)
    is used only by the fault experiments to replace a field in a model's call."""
    config = config or AgentConfig()
    result = RunResult(mode=config.mode, model=getattr(llm, "model", None))
    started = time.perf_counter()
    session.begin_run()
    messages = build_messages(question, session, data_notes)
    pending_error = False
    budget_closing = False

    def finish(status: str, answer: str | None = None) -> RunResult:
        result.status = status
        if answer is not None:
            result.answer = answer
        result.latency_s = round(time.perf_counter() - started, 3)
        result.network_retries = getattr(llm, "network_retries", 0)
        return result

    while True:
        if time.perf_counter() - started > config.task_timeout_s:
            return finish("timeout")
        if result.model_requests >= config.max_model_requests:
            return finish("budget_exhausted")
        if pending_error:
            result.repairs += 1  # this request is a repair round
            pending_error_this_round = True
        else:
            pending_error_this_round = False
        pending_error = False
        tools = None if budget_closing else TOOL_SPECS
        try:
            response = llm.chat(messages, tools)
        except LLMError as exc:
            result.error_message = str(exc)
            return finish("api_error")
        result.model_requests += 1
        _add_usage(result, response.usage)
        result.model = response.model or result.model
        result.steps.append({"type": "model", "request": result.model_requests,
                             "repair_round": pending_error_this_round, "tools_enabled": tools is not None,
                             "tool_calls": [call.name for call in response.tool_calls],
                             "content": (response.content or "")[:500]})

        if not response.tool_calls or budget_closing:
            answer = response.content or ""
            if budget_closing:
                return finish(result.status if result.status != "running" else "budget_exhausted", answer)
            if pending_error_this_round:
                return finish("unresolved", answer)  # gave up / asked for clarification after an error
            return finish("completed", answer)

        messages.append(response.assistant_message())
        failed = False
        budget_hit = False
        for call in response.tool_calls:
            if failed or result.tool_calls >= config.max_tool_calls:
                reason = "previous_call_failed" if failed else "tool_budget_exhausted"
                budget_hit = budget_hit or not failed
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps({"success": False, "skipped": True, "reason": reason})})
                result.steps.append({"type": "tool", "name": call.name, "skipped": reason})
                continue
            result.tool_calls += 1
            raw_arguments, injected = call.arguments, None
            if injector is not None:
                raw_arguments, injected = injector(call.name, raw_arguments)
            envelope = _execute(call.name, raw_arguments, session, config.mode)
            shown = result_for_model(call.name, envelope)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(shown, default=str)})
            step = {"type": "tool", "name": call.name, "arguments": raw_arguments, "T": result.tool_calls,
                    "R": result.repairs, "success": envelope.get("success", False)}
            if injected:
                step["injected"] = injected
            if envelope.get("success"):
                data = envelope["data"]
                if call.name == "aggregate_data":
                    result.result_ids.append(data["result_id"])
                    step["result_id"] = data["result_id"]
                elif call.name == "plot_result":
                    result.chart_id = data["chart_id"]
                    step["chart_id"] = data["chart_id"]
            else:
                failed = True
                error = envelope.get("error") or {}
                step["error"] = {key: error.get(key) for key in ("code", "field", "message", "error_stage")}
                if result.first_error is None:
                    result.first_error = step["error"] | {"tool": call.name, "T": result.tool_calls}
            result.steps.append(step)

        if failed:
            if config.mode == "baseline":
                return finish("tool_error")
            if result.repairs >= config.max_repairs:
                return finish("repair_exhausted")
            pending_error = True
        if result.tool_calls >= config.max_tool_calls and not pending_error:
            # One closing request without tools; status reflects whether calls were cut off.
            budget_closing = True
            result.status = "budget_exhausted" if budget_hit else "completed"
        elif result.tool_calls >= config.max_tool_calls and pending_error:
            return finish("budget_exhausted")
