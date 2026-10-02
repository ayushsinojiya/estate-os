"""Streaming STT interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Callable, Literal, Protocol


@dataclass
class STTEvent:
    kind: Literal["partial", "final", "speech_start", "speech_end", "error"]
    text: str = ""
    language: str | None = None
    confidence: float | None = None
    fatal: bool = False


class StreamingSTT(Protocol):
    name: str

    async def start(self) -> None: ...
    async def send_audio(self, mulaw_8k: bytes) -> None: ...
    def events(self) -> AsyncIterator[STTEvent]: ...
    async def close(self) -> None: ...


STTFactory = Callable[[], StreamingSTT]
