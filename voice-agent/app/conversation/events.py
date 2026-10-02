"""Caller-side events feeding the session, independent of VAD and STT vendors."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, Union


@dataclass
class SpeechStarted:
    t: float


@dataclass
class SpeechEnded:
    t: float


@dataclass
class PartialTranscript:
    text: str


@dataclass
class FinalTranscript:
    text: str
    language: str | None = None


@dataclass
class STTFailure:
    reason: str


CallerEvent = Union[SpeechStarted, SpeechEnded, PartialTranscript, FinalTranscript, STTFailure]


class CallerInput(Protocol):
    events: asyncio.Queue
    on_fallback: bool

    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def switch_to_fallback(self) -> None: ...
    def set_agent_speaking(self, speaking: bool) -> None: ...


class QueueCallerInput:
    """Events pushed directly (tests and the text simulator)."""

    def __init__(self) -> None:
        self.events: asyncio.Queue = asyncio.Queue()
        self.on_fallback = False

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def switch_to_fallback(self) -> None:
        self.on_fallback = True

    def set_agent_speaking(self, speaking: bool) -> None:
        return None

    async def say(self, text: str, duration_s: float = 0.05, language: str | None = None) -> None:
        loop = asyncio.get_running_loop()
        await self.events.put(SpeechStarted(loop.time()))
        await asyncio.sleep(duration_s)
        await self.events.put(FinalTranscript(text, language))
        await self.events.put(SpeechEnded(loop.time()))
