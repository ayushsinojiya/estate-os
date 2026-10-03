"""Offline demo brain so the pipeline runs without API keys.

This is NOT the product LLM. It answers by quoting back the last tool result it was handed, which
is enough to exercise speech and turn-taking end to end — and keeps fake mode honest, since it can
only "know" what a tool actually returned.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator

from app.llm.base import LLMEvent, Message, ToolSpec
from app.llm.fake import say

_WHITESPACE = re.compile(r"\s+")


class DemoLLM:
    def __init__(self, name: str = "demo"):
        self.name = name

    async def stream(self, messages: list[Message], tools: list[ToolSpec], *,
                     max_tokens: int = 400, temperature: float = 0.2,
                     **_: object) -> AsyncIterator[LLMEvent]:
        await asyncio.sleep(0.01)
        for event in say(self._answer(messages)):
            yield event

    @staticmethod
    def _answer(messages: list[Message]) -> str:
        """Summarise the latest tool result; never invent anything it does not contain."""
        evidence = next((m.content for m in reversed(messages) if m.role == "tool"), "")
        if not evidence:
            return "I do not have that information right now. Someone from our team will confirm it."
        # Strip JSON punctuation and table pipes so the demo reply is speakable.
        text = _WHITESPACE.sub(" ", re.sub(r"[{}\[\]\"|]", " ", evidence)).strip()
        return f"[demo answer] {text[:300]}"
