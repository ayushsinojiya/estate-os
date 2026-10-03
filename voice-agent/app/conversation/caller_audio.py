"""Production caller input: telephony audio → local VAD + streaming STT → CallerEvents.

Continuous streaming (spec section 5). STT leg samples for degradation routing: final-transcript
latency after end of speech, and request errors (error event, socket failure, or no final within
2,000 ms of end of speech; spec section 30).
"""

from __future__ import annotations

import asyncio
import logging

from app.audio.vad import EnergyVAD
from app.conversation.events import FinalTranscript, PartialTranscript, SpeechEnded, SpeechStarted, STTFailure
from app.resilience.degradation import LegMonitor
from app.stt.base import StreamingSTT, STTFactory

log = logging.getLogger(__name__)


class AudioCallerInput:
    def __init__(self, primary: STTFactory, fallback: STTFactory, vad: EnergyVAD | None = None,
                 start_on_fallback: bool = False, stt_leg: LegMonitor | None = None, final_timeout_s: float = 2.0,
                 flush_after_s: float = 0.15):
        self.events: asyncio.Queue = asyncio.Queue()
        self.on_fallback = start_on_fallback
        self._primary, self._fallback = primary, fallback
        self.vad = vad or EnergyVAD()
        self.leg = stt_leg
        self.final_timeout_s = final_timeout_s
        # STTs that support it are asked to finalise this long after our VAD reports end of speech (CL-006).
        self.flush_after_s = flush_after_s
        self._flush_at: float | None = None
        self.stt: StreamingSTT | None = None
        self._reader: asyncio.Task | None = None
        self._final_timer: asyncio.Task | None = None
        self._speech_end: float | None = None
        self._final_seen = True
        self._broken = False

    @staticmethod
    def _now() -> float:
        return asyncio.get_running_loop().time()

    async def start(self) -> None:
        await self._open(self._fallback if self.on_fallback else self._primary)

    async def _open(self, factory: STTFactory) -> None:
        # Publish the STT only once it is connected: audio pushed during connect is dropped, not failed.
        self.stt = None
        stt = factory()
        try:
            await stt.start()
        except Exception as exc:  # noqa: BLE001
            await self._failure(f"connect failed: {exc!r}")
            return
        self._broken = False
        self.stt = stt
        self._reader = asyncio.create_task(self._read(stt))

    def set_agent_speaking(self, speaking: bool) -> None:
        self.vad.agent_speaking = speaking

    async def push_audio(self, frame: bytes) -> None:
        now = self._now()
        frame_s = self.vad.cfg.frame_ms / 1000
        for event in self.vad.process(frame):
            if event == "start":
                self._flush_at = None
                await self.events.put(SpeechStarted(now - self.vad.cfg.onset_frames * frame_s))
            else:
                self._flush_at = now + self.flush_after_s
                end = now - self.vad.cfg.hangover_frames * frame_s
                self._speech_end, self._final_seen = end, False
                await self.events.put(SpeechEnded(end))
                if self._final_timer:
                    self._final_timer.cancel()
                self._final_timer = asyncio.create_task(self._watch_final())
        if self.stt is None or self._broken:
            return
        try:
            await self.stt.send_audio(frame)
            if self._flush_at is not None and now >= self._flush_at:
                self._flush_at = None
                flush = getattr(self.stt, "flush", None)
                if flush is not None:
                    await flush()
        except Exception as exc:  # noqa: BLE001
            await self._failure(f"send failed: {exc!r}")

    async def _watch_final(self) -> None:
        await asyncio.sleep(self.final_timeout_s)
        if not self._final_seen and self.leg:
            self.leg.record(self._now(), error=True, source="no_final")

    async def _read(self, stt: StreamingSTT) -> None:
        try:
            async for event in stt.events():
                if event.kind == "partial" and event.text:
                    await self.events.put(PartialTranscript(event.text))
                elif event.kind == "final" and event.text:
                    now = self._now()
                    if self.leg and self._speech_end is not None and not self._final_seen:
                        self.leg.record(now, latency_ms=max(0.0, (now - self._speech_end) * 1000))
                    self._final_seen = True
                    await self.events.put(FinalTranscript(event.text, event.language))
                elif event.kind == "error" and event.fatal:
                    await self._failure(event.text)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await self._failure(f"stream failed: {exc!r}")

    async def _failure(self, reason: str) -> None:
        if self._broken:
            return
        self._broken = True
        log.warning("STT failure on %s: %s", "fallback" if self.on_fallback else "primary", reason)
        if self.leg:
            self.leg.record(self._now(), error=True, source="stt_failure")
        await self.events.put(STTFailure(reason))

    async def switch_to_fallback(self) -> None:
        if self.on_fallback:
            return
        await self._close_current()
        self.on_fallback = True
        await self._open(self._fallback)

    async def _close_current(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self.stt:
            try:
                await self.stt.close()
            except Exception:  # noqa: BLE001
                pass

    async def close(self) -> None:
        if self._final_timer:
            self._final_timer.cancel()
        await self._close_current()
