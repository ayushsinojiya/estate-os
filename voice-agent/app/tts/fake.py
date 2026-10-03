"""TTS that returns μ-law silence, 10 ms per character (offline mode and smoke tests)."""

from __future__ import annotations

from typing import AsyncIterator

from app.audio.codecs import MULAW_SILENCE
from app.lang.languages import Lang


class SilenceTTS:
    def __init__(self, name: str = "silence_tts", ms_per_char: int = 10):
        self.name = name
        self.ms_per_char = ms_per_char

    async def synthesize(self, text: str, language: Lang) -> AsyncIterator[bytes]:
        total = len(text) * self.ms_per_char * 8
        for i in range(0, total, 800):
            yield bytes([MULAW_SILENCE]) * min(800, total - i)

    async def cancel(self) -> None:
        return None

    async def close(self) -> None:
        return None
