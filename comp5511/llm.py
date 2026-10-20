"""Model clients: DeepSeek over HTTP (OpenAI-compatible tool calling) and a
scripted FakeLLM for offline tests and the labelled offline demo."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"  # confirm against the official docs before frozen runs


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text exactly as the model produced it


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict | None = None  # None when the provider did not report usage
    latency_s: float = 0.0
    model: str | None = None

    def assistant_message(self) -> dict:
        """The assistant turn to append to messages (protocol requires tool_calls)."""
        message = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": call.id, "type": "function",
                 "function": {"name": call.name, "arguments": call.arguments}}
                for call in self.tool_calls
            ]
        return message


class LLMError(RuntimeError):
    """kind: auth, bad_request, rate_limit, server, timeout, network, protocol."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind


class DeepSeekClient:
    """Minimal chat-completions client with explicit, bounded network retries.

    Network retries are not agent repairs: they resend the same request after
    a transient failure (timeout, 429, 5xx) and are counted separately.
    """

    RETRYABLE = {429, 500, 502, 503, 504}

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None, timeout_s: float = 60.0, max_retries: int = 2,
                 temperature: float = 0.0, max_tokens: int = 1024):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise LLMError("auth", "DEEPSEEK_API_KEY is not set.")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout_s, self.max_retries = timeout_s, max_retries
        self.temperature, self.max_tokens = temperature, max_tokens
        self.network_retries = 0

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        import httpx  # imported here so offline tests do not need the package

        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_tokens": self.max_tokens, "stream": False}
        if tools:
            body["tools"] = tools
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        started = time.perf_counter()
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_s) as client:
                    response = client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
            except httpx.TimeoutException as exc:
                error = LLMError("timeout", str(exc))
            except httpx.HTTPError as exc:
                error = LLMError("network", str(exc))
            else:
                if response.status_code == 200:
                    return self._parse(response.json(), time.perf_counter() - started)
                kind = {401: "auth", 403: "auth", 400: "bad_request", 422: "bad_request",
                        429: "rate_limit"}.get(response.status_code, "server")
                error = LLMError(kind, f"HTTP {response.status_code}: {response.text[:300]}")
                if response.status_code not in self.RETRYABLE:
                    raise error
            if attempt == self.max_retries:
                raise error
            self.network_retries += 1
            time.sleep(2 ** attempt)  # 1 s, then 2 s
        raise LLMError("network", "unreachable")

    @staticmethod
    def _parse(payload: dict, latency_s: float) -> LLMResponse:
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            calls = [ToolCall(call["id"], call["function"]["name"], call["function"].get("arguments") or "{}")
                     for call in message.get("tool_calls") or []]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("protocol", f"Unexpected response shape: {exc}") from None
        return LLMResponse(content=message.get("content"), tool_calls=calls,
                           finish_reason=choice.get("finish_reason"), usage=payload.get("usage"),
                           latency_s=latency_s, model=payload.get("model"))


class FakeLLM:
    """Replays a fixed script. Each step is either a string (final text answer)
    or a list of (tool_name, arguments_dict) tuples (one response with tool calls).
    A callable step receives the messages so far and returns such a step."""

    def __init__(self, script: list, model: str = "fake-llm"):
        self.script = list(script)
        self.model = model
        self.requests: list[list[dict]] = []
        self.network_retries = 0

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.requests.append(json.loads(json.dumps(messages)))
        if not self.script:
            raise LLMError("protocol", "FakeLLM script exhausted.")
        step = self.script.pop(0)
        if callable(step):
            step = step(messages)
        if isinstance(step, LLMError):
            raise step
        if isinstance(step, str):
            return LLMResponse(content=step, finish_reason="stop", model=self.model,
                               usage={"prompt_tokens": 0, "completion_tokens": 0})
        number = len(self.requests)
        calls = [ToolCall(f"call_{number}_{index}", name,
                          arguments if isinstance(arguments, str) else json.dumps(arguments))
                 for index, (name, arguments) in enumerate(step)]
        return LLMResponse(content="", tool_calls=calls, finish_reason="tool_calls", model=self.model,
                           usage={"prompt_tokens": 0, "completion_tokens": 0})
