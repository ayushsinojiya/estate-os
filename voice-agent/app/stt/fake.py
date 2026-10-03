"""STT that never transcribes (offline mode and smoke tests)."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.stt.base import STTEvent


class SilentSTT:
    def __init__(self) -> None:
        self.name = "silent_stt"
        self._closed = asyncio.Event()

    async def start(self) -> None:
        return None

    async def send_audio(self, mulaw_8k: bytes) -> None:
        return None

    async def events(self) -> AsyncIterator[STTEvent]:
        await self._closed.wait()
        return
        yield  # pragma: no cover - makes this an async generator

    async def close(self) -> None:
        self._closed.set()
