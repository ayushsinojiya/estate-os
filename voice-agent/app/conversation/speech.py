"""Speech output: paced audio playback over telephony, or text (tests and simulator).

Playback is paced at real time with a small lead so the session knows when audio has actually
finished playing (needed for the read-back early-answer rule) and can stop instantly on barge-in.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Protocol

from app.audio.codecs import MULAW_SILENCE, apply_gain_mulaw
from app.lang.languages import Lang
from app.telephony.base import CallTransport
from app.tts.base import FailoverTTS, TTSError
from app.tts.cache import PhraseAudioCache

log = logging.getLogger(__name__)
FRAME = 160  # 20 ms of 8 kHz μ-law


@dataclass
class PlaybackResult:
    completed: bool
    started_at: float
    ended_at: float
    first_audio_at: float | None
    chars: int
    error: str | None = None


class SpeechOutput(Protocol):
    @property
    def speaking(self) -> bool: ...

    async def speak_text(self, text: str, lang: Lang, phrase_key: str | None = None) -> PlaybackResult: ...
    async def speak_stream(self, texts: AsyncIterator[str], lang: Lang) -> PlaybackResult: ...
    async def stop(self) -> None: ...


async def _one(data: bytes) -> AsyncIterator[bytes]:
    yield data


class AudioSpeechOutput:
    def __init__(self, transport: CallTransport, tts: FailoverTTS, cache: PhraseAudioCache | None = None,
                 lead_s: float = 0.12, on_speaking: Callable[[bool], None] | None = None,
                 output_gain: float = 1.0):
        self.transport = transport
        self.tts = tts
        self.cache = cache
        self.lead_s = lead_s
        self.on_speaking = on_speaking
        self.output_gain = output_gain
        self._active = 0
        self._play_end = 0.0
        self.synth_chars = 0  # characters sent to the TTS provider during this call (cost log)
        # One clip at a time: two plays sharing the line would interleave their frames.
        self._line = asyncio.Lock()

    def _framed(self, chunk: bytes) -> bytes:
        return apply_gain_mulaw(chunk, self.output_gain) if self.output_gain != 1.0 else chunk

    @property
    def speaking(self) -> bool:
        return self._active > 0

    def _set(self, delta: int) -> None:
        before = self.speaking
        self._active += delta
        if self.on_speaking and before != self.speaking:
            self.on_speaking(self.speaking)

    async def speak_text(self, text: str, lang: Lang, phrase_key: str | None = None) -> PlaybackResult:
        cached = self.cache.get(phrase_key, lang) if self.cache else None
        if not cached:
            self.synth_chars += len(text)  # billed by the TTS provider; a cache hit is free
        return await self._play(_one(cached) if cached else self.tts.synthesize(text, lang), len(text))

    async def speak_stream(self, texts: AsyncIterator[str], lang: Lang) -> PlaybackResult:
        """Speak sentences as they arrive. Each is synthesised as soon as it is known, while the
        previous one is still playing, so there is no synthesis gap between sentences."""
        audio: asyncio.Queue = asyncio.Queue()
        chars = 0

        async def synthesise() -> None:
            nonlocal chars
            try:
                async for text in texts:
                    chars += len(text)
                    self.synth_chars += len(text)
                    async for chunk in self.tts.synthesize(text, lang):
                        await audio.put(chunk)
                await audio.put(None)
            except BaseException as exc:  # noqa: BLE001 - handed to the player, which re-raises
                await audio.put(exc)
                if isinstance(exc, asyncio.CancelledError):
                    raise

        async def drain() -> AsyncIterator[bytes]:
            while (item := await audio.get()) is not None:
                if isinstance(item, BaseException):
                    raise item
                yield item

        producer = asyncio.create_task(synthesise())
        try:
            result = await self._play(drain(), 0)
            result.chars = chars
            return result
        finally:
            producer.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await producer

    async def _play(self, source: AsyncIterator[bytes], chars: int) -> PlaybackResult:
        async with self._line:
            return await self._play_locked(source, chars)

    async def _play_locked(self, source: AsyncIterator[bytes], chars: int) -> PlaybackResult:
        loop = asyncio.get_running_loop()
        start = loop.time()
        first_audio = None
        self._set(+1)
        try:
            leftover = b""
            async for chunk in source:
                data = leftover + chunk
                usable = len(data) // FRAME * FRAME
                leftover = data[usable:]
                for i in range(0, usable, FRAME):
                    ahead = self._play_end - loop.time()
                    if ahead > self.lead_s:
                        await asyncio.sleep(ahead - self.lead_s)
                    if first_audio is None:
                        first_audio = loop.time()
                    await self.transport.send_audio(self._framed(data[i:i + FRAME]))
                    self._play_end = max(self._play_end, loop.time()) + FRAME / 8000
            if leftover:
                await self.transport.send_audio(self._framed(leftover) + bytes([MULAW_SILENCE]) * (FRAME - len(leftover)))
                self._play_end = max(self._play_end, loop.time()) + FRAME / 8000
            remaining = self._play_end - loop.time()
            if remaining > 0:
                await asyncio.sleep(remaining)
            return PlaybackResult(True, start, loop.time(), first_audio, chars)
        except TTSError as exc:
            log.error("TTS unavailable: %s", exc)
            return PlaybackResult(False, start, loop.time(), first_audio, chars, error="tts_unavailable")
        finally:
            self._set(-1)

    async def stop(self) -> None:
        self._play_end = asyncio.get_running_loop().time()
        await self.transport.clear_audio()
        await self.tts.cancel()


class TextSpeechOutput:
    def __init__(self, seconds_per_char: float = 0.0, on_text: Callable[[str], None] | None = None):
        self.seconds_per_char = seconds_per_char
        self.on_text = on_text
        self.started: list[str] = []
        self.completed: list[str] = []
        self.interrupted: list[str] = []
        self.stops = 0
        self._active = 0

    @property
    def speaking(self) -> bool:
        return self._active > 0

    async def speak_text(self, text: str, lang: Lang, phrase_key: str | None = None) -> PlaybackResult:
        loop = asyncio.get_running_loop()
        start = loop.time()
        self._active += 1
        self.started.append(text)
        if self.on_text:
            self.on_text(text)
        try:
            await asyncio.sleep(len(text) * self.seconds_per_char)
        except asyncio.CancelledError:
            self.interrupted.append(text)
            raise
        finally:
            self._active -= 1
        self.completed.append(text)
        return PlaybackResult(True, start, loop.time(), start, len(text))

    async def speak_stream(self, texts: AsyncIterator[str], lang: Lang) -> PlaybackResult:
        start = asyncio.get_running_loop().time()
        chars = 0
        async for text in texts:
            chars += (await self.speak_text(text, lang)).chars
        return PlaybackResult(True, start, asyncio.get_running_loop().time(), start, chars)

    async def stop(self) -> None:
        self.stops += 1
