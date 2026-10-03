"""Rumik Silk Mulberry 1.5 streaming TTS (primary, spec section 6).

POST https://silk-api.rumik.ai/v1/tts/ws-connect (Bearer key) returns {ws_url, token}; connect to
ws_url?token=... and send {"text", "model", "description"} frames. Audio arrives as binary frames
in the negotiated format (mulaw = raw 8 kHz G.711), then {"type": "done"}. Sending new text while
generating interrupts the old request (latest wins); {"type": "cancel"} stops generation.

ASSUMPTION: ws-connect requires `text`, so the first utterance is passed there too. If Rumik
starts generating from that alone, the explicit frame supersedes it (latest wins) and a
"cancelled" frame for the first request is ignored.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.lang.languages import Lang
from app.tts.base import TTSError

log = logging.getLogger(__name__)


class RumikTTS:
    def __init__(self, api_key: str, base_url: str, model: str, description: str, speaker: str = "",
                 http: httpx.AsyncClient | None = None):
        self.name = "rumik"
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._model = model
        self._description = description
        self._speaker = speaker
        self._http = http or httpx.AsyncClient(timeout=5.0)
        self._ws = None
        self._drain_before_next = False
        self._lock = asyncio.Lock()

    async def _connect(self, first_text: str) -> None:
        resp = await self._http.post(f"{self._base}/v1/tts/ws-connect",
                                     headers={"Authorization": f"Bearer {self._api_key}"},
                                     json={"model": self._model, "text": first_text[:2000], "audio_format": "mulaw"})
        if resp.status_code != 200:
            raise TTSError(f"rumik ws-connect {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        self._ws = await connect(f"{data['ws_url']}?token={data['token']}", open_timeout=5, max_size=None)
        self._drain_before_next = False

    async def _drain(self) -> None:
        try:
            while True:
                msg = await asyncio.wait_for(self._ws.recv(), 0.5)
                if isinstance(msg, str) and json.loads(msg).get("type") in ("cancelled", "done"):
                    return
        except (asyncio.TimeoutError, ConnectionClosed):
            return

    async def synthesize(self, text: str, language: Lang) -> AsyncIterator[bytes]:
        async with self._lock:
            if self._ws is None or self._ws.state.name != "OPEN":
                await self._connect(text)
            elif self._drain_before_next:
                await self._drain()
                self._drain_before_next = False
            frame = {"text": text, "model": self._model, "description": self._description}
            if self._speaker:
                frame["speaker"] = self._speaker
            try:
                await self._ws.send(json.dumps(frame, ensure_ascii=False))
                async for msg in self._ws:
                    if isinstance(msg, bytes):
                        yield msg
                        continue
                    data = json.loads(msg)
                    kind = data.get("type")
                    if kind == "done":
                        return
                    if kind == "cancelled":
                        continue  # an older request (or the ws-connect text) was superseded
                    if kind == "timeout" or data.get("error"):
                        raise TTSError(f"rumik error: {data}")
            except ConnectionClosed as exc:
                self._ws = None
                raise TTSError(f"rumik socket closed: {exc}") from exc
            except asyncio.CancelledError:
                self._drain_before_next = True
                raise

    async def cancel(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "cancel"}))
                self._drain_before_next = True
            except ConnectionClosed:
                self._ws = None

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "close"}))
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
        await self._http.aclose()
