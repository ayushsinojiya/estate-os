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
import re
import logging
from typing import AsyncIterator

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.lang.languages import Lang
from app.tts.base import TTSError

log = logging.getLogger(__name__)


# Spellings Mulberry pronounces recognisably, chosen by measurement: each word was synthesised in
# several spellings (speaker siya, temperature 0.4) and the audio transcribed by Sarvam STT. Latin won
# for "site visit" (4/4 vs 0/4 for साइट विजिट), "slot" (2/2 vs 0/2 for स्लॉट) and "amenities";
# Devanagari won for possession (पज़ेशन 2/2, Latin 0/2), assistant and area. Applied to every text,
# after the engine's own Devanagari speech conversion.
_PRONUNCIATION: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.I), r) for p, r in [
        (r"(?:साइट|साईट|site)[\s-]*(?:विज़िट|विजिट|वीज़िट|visit)(?:्स)?", "site visit"),
        (r"(?<![\w\u0900-\u097f])(?:विज़िट|विजिट|वीज़िट)(?![\u0900-\u097f])", "visit"),
        (r"(?<![\w\u0900-\u097f])(?:स्लॉट्स|स्लोट्स)(?![\u0900-\u097f])", "slots"),
        (r"(?<![\w\u0900-\u097f])(?:स्लॉट|स्लोट)(?![\u0900-\u097f])", "slot"),
        (r"(?<![\w\u0900-\u097f])(?:अमेनिटीज़|अमेनिटीज|एमेनिटीज़|एमेनिटीज)(?![\u0900-\u097f])", "amenities"),
        (r"\bpossession\b|(?<![\u0900-\u097f])(?:पोज़ेशन|पोजेशन|पजेशन|पोसेशन)(?![\u0900-\u097f])", "पज़ेशन"),
        # Chosen by ear (ira, mia, sophia): "assistent" in Latin; every Devanagari spelling sounded off.
        (r"\bassistants?\b|(?<![\u0900-\u097f])(?:असिस्टेंट|असिस्टैंट|असिस्टन्ट|एसिस्टेंट)(?![\u0900-\u097f])", "assistent"),
        (r"\bareas?\b|(?<![\u0900-\u097f])एरीया(?![\u0900-\u097f])", "एरिया"),
        # "एआई" was recognised 1/3, "AI" / "A I" 3/3; "रेरा" 3/3 vs "RERA" 2/3.
        (r"(?<![\u0900-\u097f])एआई(?![\u0900-\u097f])", "AI"),
        (r"\bRERA\b", "रेरा"),
        # "ब्रोशर" 3/3 with mia and sophia; Latin "brochure" 2/3 with sophia.
        (r"\bbrochures?\b", "ब्रोशर"),
        # Pune localities: Latin was misread for these six; Devanagari for the others was (by STT,
        # sophia, 2026-10-04). Hinjewadi, Wagholi, Kothrud stay Latin.
        (r"\b[WV]akad\b|(?<![\u0900-\u097f])(?:वाकड़|वाकड)(?![\u0900-\u097f])", "वाकड"),
        (r"\bBaner\b|(?<![\u0900-\u097f])(?:बानेर|बाणेर)(?![\u0900-\u097f])", "बाणेर"),
        (r"\bKharadi\b|(?<![\u0900-\u097f])(?:खराड़ी|खराडी)(?![\u0900-\u097f])", "खराडी"),
        (r"\bRavet\b|(?<![\u0900-\u097f])(?:रावेत|रावेट)(?![\u0900-\u097f])", "रावेट"),
        (r"\bHadapsar\b|(?<![\u0900-\u097f])(?:हडपसर|हड़पसर)(?![\u0900-\u097f])", "हड़पसर"),
        (r"\bMagarpatta\b|(?<![\u0900-\u097f])(?:मगरपट्टा|मगरपट्ट)(?![\u0900-\u097f])", "मगरपट्टा"),
        (r"(?<![\u0900-\u097f])(?:हिंजवडी|हिंजेवाड़ी|हिंजवाड़ी|हिंजेवाडी)(?![\u0900-\u097f])", "Hinjewadi"),
        (r"(?<![\u0900-\u097f])(?:वाघोली|वाघौली)(?![\u0900-\u097f])", "Wagholi"),
        (r"(?<![\u0900-\u097f])(?:कोथरूड|कोथरुड)(?![\u0900-\u097f])", "Kothrud"),
    ]
]


def rumik_pronunciation(text: str) -> str:
    for pattern, replacement in _PRONUNCIATION:
        text = pattern.sub(replacement, text)
    return text


class RumikTTS:
    def __init__(self, api_key: str, base_url: str, model: str, description: str, speaker: str = "",
                 http: httpx.AsyncClient | None = None, temperature: float | None = None):
        self.name = "rumik"
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._model = model
        self._description = description
        # Without a preset speaker the voice is rebuilt from the description on every request, so its
        # pitch drifts from sentence to sentence; a speaker (and a lower temperature) keeps it steady.
        self._speaker = speaker
        self._temperature = temperature
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
        text = rumik_pronunciation(text)
        async with self._lock:
            if self._ws is None or self._ws.state.name != "OPEN":
                await self._connect(text)
            elif self._drain_before_next:
                await self._drain()
                self._drain_before_next = False
            frame = {"text": text, "model": self._model, "description": self._description}
            if self._speaker:
                frame["speaker"] = self._speaker
            if self._temperature is not None:
                frame["temperature"] = self._temperature
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
