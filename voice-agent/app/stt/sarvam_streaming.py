"""Sarvam Saaras v3 streaming STT over wss://api.sarvam.ai/speech-to-text/ws (primary, spec section 5; CL-006).

Replaces the `speech-to-text-realtime` socket: on replayed call audio its finals arrived ~600-970 ms after
end of speech, versus ~300-620 ms here with `high_vad_sensitivity` and a client flush sent shortly after our
own VAD sees silence. Audio is sent as 8 kHz PCM16 little-endian:
{"audio": {"data": base64, "sample_rate": "8000", "encoding": "audio/wav"}}. Server messages are
{"type": "data" | "events" | "error", "data": {...}}.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, AsyncIterator
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.audio.codecs import mulaw_to_pcm16
from app.stt.base import STTEvent

log = logging.getLogger(__name__)

_LANGS = {"mr", "hi", "en", "gu"}


def language_of(code: str | None) -> str | None:
    base = (code or "").split("-")[0].lower()
    return base if base in _LANGS else None


def parse_message(msg: dict[str, Any]) -> STTEvent | None:
    kind, data = msg.get("type"), msg.get("data") or {}
    if kind == "data":
        prob = data.get("language_probability")
        try:
            confidence = float(prob) if prob is not None else None
        except (TypeError, ValueError):
            confidence = None
        return STTEvent("final", (data.get("transcript") or "").strip(), language_of(data.get("language_code")), confidence)
    if kind == "events":
        signal = data.get("signal_type")
        if signal == "START_SPEECH":
            return STTEvent("speech_start")
        if signal == "END_SPEECH":
            return STTEvent("speech_end")
        return None
    if kind == "error":
        return STTEvent("error", str(data.get("error") or data.get("message") or "error"), fatal=False)
    return None


class SarvamStreamingSTT:
    def __init__(self, api_key: str, ws_url: str = "wss://api.sarvam.ai/speech-to-text/ws", model: str = "saaras:v3",
                 language_code: str = "unknown", mode: str = "codemix", high_vad_sensitivity: bool = True,
                 chunk_ms: int = 20):
        self.name = "sarvam_stt"
        self._api_key = api_key
        self._params = {
            "model": model, "mode": mode, "language-code": language_code, "sample_rate": "8000",
            "input_audio_codec": "pcm_s16le", "vad_signals": "true", "flush_signal": "true",
            "high_vad_sensitivity": "true" if high_vad_sensitivity else "false",
        }
        self._url = ws_url
        self._chunk_bytes = 8 * chunk_ms
        self._buffer = b""
        self._queue: asyncio.Queue[STTEvent | None] = asyncio.Queue()
        self._ws = None
        self._reader: asyncio.Task | None = None

    async def start(self) -> None:
        self._ws = await connect(f"{self._url}?{urlencode(self._params)}",
                                 additional_headers={"Api-Subscription-Key": self._api_key}, open_timeout=5, max_size=None)
        self._reader = asyncio.create_task(self._receive())

    async def send_audio(self, mulaw_8k: bytes) -> None:
        self._buffer += mulaw_8k
        while len(self._buffer) >= self._chunk_bytes:
            chunk, self._buffer = self._buffer[:self._chunk_bytes], self._buffer[self._chunk_bytes:]
            pcm = mulaw_to_pcm16(chunk).astype("<i2").tobytes()
            await self._ws.send(json.dumps({"audio": {"data": base64.b64encode(pcm).decode(), "sample_rate": "8000",
                                                      "encoding": "audio/wav"}}))

    async def flush(self) -> None:
        """Ask the server to finalise what it has heard so far."""
        if self._ws is not None:
            await self._ws.send(json.dumps({"type": "flush"}))

    async def _receive(self) -> None:
        try:
            async for raw in self._ws:
                event = parse_message(json.loads(raw))
                if event is None:
                    continue
                if event.kind == "error":
                    log.warning("Sarvam STT error: %s", event.text)
                await self._queue.put(event)
        except ConnectionClosed as exc:
            if exc.rcvd is None or exc.rcvd.code != 1000:
                await self._queue.put(STTEvent("error", f"socket closed: {exc}", fatal=True))
        finally:
            await self._queue.put(None)

    async def events(self) -> AsyncIterator[STTEvent]:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
