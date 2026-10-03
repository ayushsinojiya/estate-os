"""Sarvam Bulbul v3 streaming TTS (primary TTS, CL-004).

Protocol from the official sarvamai SDK (0.1.33):
- wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3&send_completion_event=true, header Api-Subscription-Key
- client: {"type": "config", "data": {...}}, {"type": "text", "data": {"text"}}, {"type": "flush"}, {"type": "ping"}
- server: {"type": "audio", "data": {"content_type", "audio": base64}}, {"type": "event", "data": {"event_type": "final"}},
          {"type": "error", "data": {"message"}}
Output is requested as 8 kHz μ-law so no conversion is needed. There is no server-side cancel: on barge-in the
socket is dropped and a fresh one is pre-opened in the background, so the next reply skips the connect cost.
The server closes idle sockets after one minute; a ping keeps the call's socket alive.
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

from app.audio.codecs import to_mulaw_8k
from app.lang.languages import Lang
from app.tts.base import TTSError

log = logging.getLogger(__name__)

LANGUAGE_CODES = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN", "gu": "gu-IN"}


async def _close_quietly(ws: Any) -> None:
    try:
        await ws.close()
    except Exception:  # noqa: BLE001
        pass


class SarvamStreamingTTS:
    def __init__(self, api_key: str, ws_url: str = "wss://api.sarvam.ai/text-to-speech/ws", model: str = "bulbul:v3",
                 speaker: str = "ishita", pace: float = 1.0, enable_preprocessing: bool = True,
                 connect_timeout_s: float = 5.0, ping_interval_s: float = 25.0):
        self.name = "sarvam_streaming_tts"
        self._api_key = api_key
        self._ws_url = ws_url
        self._model = model
        self._speaker = speaker
        self._pace = pace
        self._preprocessing = enable_preprocessing
        self._connect_timeout_s = connect_timeout_s
        self._ping_interval_s = ping_interval_s
        self._ws: Any = None
        self._spare: asyncio.Task | None = None
        self._pinger: asyncio.Task | None = None
        self._configured_lang: str | None = None
        self._lock = asyncio.Lock()

    # ---- connection management
    async def _open(self) -> Any:
        url = f"{self._ws_url}?{urlencode({'model': self._model, 'send_completion_event': 'true'})}"
        return await connect(url, additional_headers={"Api-Subscription-Key": self._api_key},
                             open_timeout=self._connect_timeout_s, max_size=None)

    def warm(self) -> None:
        """Pre-open a socket in the background (call start, and after a barge-in)."""
        if self._ws is None and (self._spare is None or self._spare.done()):
            self._spare = asyncio.create_task(self._open())

    async def _socket(self) -> Any:
        if self._ws is not None and self._ws.state.name == "OPEN":
            return self._ws
        self._ws, self._configured_lang = None, None
        if self._spare is not None:
            spare, self._spare = self._spare, None
            try:
                self._ws = await spare
            except Exception as exc:  # noqa: BLE001 - fall through to a fresh connect
                log.info("spare Sarvam TTS socket failed: %r", exc)
        if self._ws is None:
            self._ws = await self._open()
        if self._pinger is None or self._pinger.done():
            self._pinger = asyncio.create_task(self._ping())
        return self._ws

    def _drop(self) -> None:
        ws, self._ws, self._configured_lang = self._ws, None, None
        if ws is not None:
            asyncio.get_running_loop().create_task(_close_quietly(ws))
        self.warm()

    async def _ping(self) -> None:
        while True:
            await asyncio.sleep(self._ping_interval_s)
            if self._ws is not None:
                try:
                    await self._ws.send(json.dumps({"type": "ping"}))
                except Exception:  # noqa: BLE001
                    self._ws = None

    async def _configure(self, ws: Any, lang: Lang) -> None:
        if self._configured_lang == lang:
            return
        data = {"model": self._model, "language_code": LANGUAGE_CODES[lang], "speaker": self._speaker, "pace": self._pace,
                "speech_sample_rate": 8000, "output_audio_codec": "mulaw", "min_buffer_size": 50, "max_chunk_length": 150,
                "enable_preprocessing": self._preprocessing}
        await ws.send(json.dumps({"type": "config", "data": data}))
        self._configured_lang = lang

    # ---- synthesis
    async def synthesize(self, text: str, language: Lang) -> AsyncIterator[bytes]:
        async with self._lock:
            try:
                ws = await self._socket()
                await self._configure(ws, language)
                await ws.send(json.dumps({"type": "text", "data": {"text": text}}, ensure_ascii=False))
                await ws.send(json.dumps({"type": "flush"}))
                async for raw in ws:
                    if not isinstance(raw, str):
                        continue
                    msg = json.loads(raw)
                    kind = msg.get("type")
                    data = msg.get("data") or {}
                    if kind == "audio":
                        audio = base64.b64decode(data.get("audio", ""))
                        if audio:
                            yield to_mulaw_8k(audio) if audio[:4] == b"RIFF" else audio
                    elif kind == "event" and data.get("event_type") == "final":
                        return
                    elif kind == "error":
                        self._drop()
                        raise TTSError(f"sarvam tts error: {data.get('message')}")
                self._drop()
                raise TTSError("sarvam tts socket closed mid-utterance")
            except ConnectionClosed as exc:
                self._drop()
                raise TTSError(f"sarvam tts socket closed: {exc}") from exc
            except (OSError, asyncio.TimeoutError) as exc:
                self._drop()
                raise TTSError(f"sarvam tts connect failed: {exc!r}") from exc
            except (asyncio.CancelledError, GeneratorExit):
                self._drop()  # abandoned mid-utterance: this socket still has audio queued
                raise

    async def cancel(self) -> None:
        if self._ws is not None:
            self._drop()

    async def close(self) -> None:
        for task in (self._pinger, self._spare):
            if task is not None:
                task.cancel()
        if self._ws is not None:
            await _close_quietly(self._ws)
            self._ws = None
