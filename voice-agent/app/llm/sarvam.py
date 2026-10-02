"""Sarvam chat completions (primary LLM, spec section 7).

POST https://api.sarvam.ai/v1/chat/completions, header api-subscription-key, SSE streaming with
OpenAI-style chunk deltas. Step 1 of the ladder sends reasoning_effort: null (thinking off).
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.llm.base import (Finished, InvalidRequest, LLMEvent, Message, ProviderUnavailable, RateLimited, TextDelta,
                          ToolCall, ToolCallReady, ToolCallStarted, ToolSpec, Usage)


def to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append({
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                               for c in m.tool_calls],
            })
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class SarvamLLM:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.sarvam.ai",
                 reasoning_effort: str | None = None, client: httpx.AsyncClient | None = None, timeout_s: float = 30.0):
        self.name = "sarvam"
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._url = base_url.rstrip("/") + "/v1/chat/completions"
        self._headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0))

    def payload(self, messages: list[Message], tools: list[ToolSpec], max_tokens: int, temperature: float) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(messages),
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning_effort": self.reasoning_effort,  # None serialises as null: thinking disabled
        }
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in tools]
            body["tool_choice"] = "auto"
        return body

    async def stream(self, messages: list[Message], tools: list[ToolSpec], *, max_tokens: int = 400,
                     temperature: float = 0.3) -> AsyncIterator[LLMEvent]:
        body = self.payload(messages, tools, max_tokens, temperature)
        tool_acc: dict[int, dict[str, str]] = {}
        finish = "stop"
        try:
            async with self._client.stream("POST", self._url, headers=self._headers, json=body) as resp:
                if resp.status_code == 429:
                    raise RateLimited("sarvam 429")
                if resp.status_code >= 500:
                    raise ProviderUnavailable(f"sarvam {resp.status_code}")
                if resp.status_code >= 400:
                    detail = (await resp.aread()).decode("utf-8", "replace")[:500]
                    raise InvalidRequest(f"sarvam {resp.status_code}: {detail}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    usage = chunk.get("usage")
                    if usage:
                        details = usage.get("prompt_tokens_details") or {}
                        yield Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                                    details.get("cached_tokens", 0))
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            yield TextDelta(delta["content"])
                        for tc in delta.get("tool_calls") or []:
                            acc = tool_acc.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                            if tc.get("id"):
                                acc["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            started = not acc["name"] and fn.get("name")
                            acc["name"] += fn.get("name") or ""
                            if started:
                                yield ToolCallStarted(acc["name"])
                            acc["arguments"] += fn.get("arguments") or ""
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderUnavailable(f"sarvam transport: {exc}") from exc
        for index in sorted(tool_acc):
            acc = tool_acc[index]
            yield ToolCallReady(ToolCall(id=acc["id"] or f"call_{index}", name=acc["name"], arguments=acc["arguments"] or "{}"))
        yield Finished(finish)
