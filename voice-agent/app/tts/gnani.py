"""Gnani Vachana (Timbre v2.5) streaming TTS — experiment.

wss://api.vachana.ai/api/v1/tts with header X-API-Key-ID. One connection serves requests one after
another: send {"text", "voice", "model", "language", "speed", "audio_config"}, receive
{"type": "start"}, {"type": "audio", "data": {"audio": <base64>}} chunks and {"type": "complete"}.
Audio is requested as raw 8 kHz μ-law, the phone's own format. There is no cancel message, so a
barge-in closes the connection and the next sentence opens a new one.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import AsyncIterator

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.lang.languages import Lang
from app.tts.base import TTSError

log = logging.getLogger(__name__)

LANGUAGE_CODES = {"hi": "hi-IN", "mr": "mr-IN", "en": "en-IN"}


class GnaniTTS:
    URL = "wss://api.vachana.ai/api/v1/tts"

    def __init__(self, api_key: str, voices: dict[str, str], model: str = "timbre-v2.5", speed: float = 1.0,
                 url: str = URL, languages: dict[str, str] | None = None):
        self.name = "gnani"
        self._headers = {"X-API-Key-ID": api_key}
        self._voices = voices
        self._languages = {**LANGUAGE_CODES, **(languages or {})}
        self._model = model
        self._speed = speed
        self._url = url
        self._ws = None
        self._lock = asyncio.Lock()

    def request(self, text: str, language: Lang) -> dict:
        return {
            "text": text, "voice": self._voices.get(language) or self._voices.get("hi", "Nalini"),
            "model": self._model, "language": self._languages.get(language, "hi-IN"), "speed": self._speed,
            "audio_config": {"sample_rate": 8000, "num_channels": 1, "sample_width": 1,
                             "encoding": "pcm_mulaw", "container": "raw"},
        }

    async def _open(self) -> None:
        if self._ws is None or self._ws.state.name != "OPEN":
            self._ws = await connect(self._url, additional_headers=self._headers, open_timeout=5,
                                     max_size=None, ping_interval=20, ping_timeout=20)

    async def synthesize(self, text: str, language: Lang) -> AsyncIterator[bytes]:
        async with self._lock:
            await self._open()
            try:
                await self._ws.send(json.dumps(self.request(text, language), ensure_ascii=False))
                async for msg in self._ws:
                    if isinstance(msg, bytes):
                        yield msg
                        continue
                    data = json.loads(msg)
                    kind = data.get("type")
                    if kind == "audio":
                        audio = (data.get("data") or {}).get("audio")
                        if audio:
                            yield base64.b64decode(audio)
                    elif kind == "complete":
                        audio = (data.get("data") or {}).get("audio")
                        if audio:
                            yield base64.b64decode(audio)
                        return
                    elif kind == "error":
                        raise TTSError(f"gnani tts: {data.get('message')}")
            except ConnectionClosed as exc:
                self._ws = None
                raise TTSError(f"gnani socket closed: {exc}") from exc
            except asyncio.CancelledError:
                # Interrupted mid-sentence: the rest of this audio would arrive before the next
                # sentence's, so drop the connection.
                await self.cancel()
                raise

    async def cancel(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def close(self) -> None:
        await self.cancel()
