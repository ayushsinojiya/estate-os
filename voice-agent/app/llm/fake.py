"""Scripted LLM for tests."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncIterator, Callable, Union

from app.llm.base import Finished, LLMEvent, Message, TextDelta, ToolCall, ToolCallReady, ToolCallStarted, ToolSpec

Step = Union[list[LLMEvent], Callable[[list[Message]], list[LLMEvent]]]


def say(*chunks: str) -> list[LLMEvent]:
    return [TextDelta(c) for c in chunks] + [Finished("stop")]


def call(name: str, **arguments) -> list[LLMEvent]:
    return [ToolCallStarted(name), ToolCallReady(ToolCall(id=f"call_{uuid.uuid4().hex[:6]}", name=name,
                                   arguments=json.dumps(arguments, ensure_ascii=False))), Finished("tool_calls")]


class ScriptedLLM:
    def __init__(self, steps: list[Step] | None = None, name: str = "scripted", first_event_delay_s: float = 0.0,
                 error: Exception | None = None):
        self.name = name
        self.steps = list(steps or [])
        self.first_event_delay_s = first_event_delay_s
        self.error = error
        self.calls: list[list[Message]] = []

    async def stream(self, messages: list[Message], tools: list[ToolSpec], *, max_tokens: int = 400,
                     temperature: float = 0.3) -> AsyncIterator[LLMEvent]:
        self.calls.append(list(messages))
        if self.error:
            raise self.error
        if self.first_event_delay_s:
            await asyncio.sleep(self.first_event_delay_s)
        step = self.steps.pop(0) if self.steps else say("ठीक आहे.")
        if callable(step):
            step = step(messages)
        for event in step:
            yield event
