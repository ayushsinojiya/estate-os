"""VoiceLink adapter.

CONFIRMED from VoiceLink's OpenAPI spec (received 2026-09-15):
- Base URL https://app.voicelink.co.in/api; POST /v1/auth/login {username, password} returns a
  Sanctum bearer token (no static API key).
- Outbound calls are queued with POST /v1/add_lead {did_number, customer_number, country_code,
  custom_parameters (JSON string), websocket_url, webhook_url}; VoiceLink's dialer places them.
- Per-client outbound queue pause/resume: /v1/websocket-management/{pause,resume}/{clientId}.
- Websocket bots (websocket_url, webhook_url, audio_format alaw|ulaw|l16|l16_16k, noise_cancel) and
  per-DID call routing to a bot; call details by call_id.

OBSERVED on the first live calls (2026-09-15):
- start: {event, sequence_number, stream_sid, timestamp, start: {stream_sid, call_sid, account_sid,
  from, to, timestamp, custom_parameters: {campaignId, callType, botId, clientId},
  media_format: {encoding, sample_rate}}}
- stop:  {event, sequenceNumber, streamSid, timestamp, stop: {accountSid, call_sid, timestamp}}
- webhooks: call.initiated / call.answered / call.ended / call.completed with call.id and recordingUrl.

The wire audio encoding follows media_format when it names a codec; otherwise it is detected from
the audio (app/telephony/wire_format.py). Audio is sent back in the same format, keyed by stream_sid,
in 100 ms chunks. Hangup closes the media socket (no hangup endpoint exists).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import WebSocket

from app.telephony.base import CallStart
from app.telephony.wire_format import CodecDetector, WireFormat, format_from_media_format

log = logging.getLogger(__name__)

START_EVENTS = {"start", "call_start", "callstart", "started", "call.started"}
STOP_EVENTS = {"stop", "end", "hangup", "call_end", "callend", "closed", "call.ended", "disconnect"}


class VoiceLinkError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"VoiceLink {status}: {detail}")
        self.status = status


def _find_token(data: Any) -> str | None:
    if isinstance(data, dict):
        for key in ("token", "access_token", "plainTextToken", "bearer_token"):
            if isinstance(data.get(key), str) and data[key]:
                return data[key]
        for value in data.values():
            if (found := _find_token(value)) is not None:
                return found
    return None


class VoiceLinkClient:
    def __init__(self, base_url: str, username: str, password: str, client: httpx.AsyncClient | None = None,
                 timeout_s: float = 10.0):
        self._http = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_s)
        self._username = username
        self._password = password
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def login(self) -> str:
        resp = await self._http.post("/v1/auth/login", json={"username": self._username, "password": self._password},
                                     headers={"Accept": "application/json"})
        if resp.status_code != 200:
            raise VoiceLinkError(resp.status_code, "login failed")
        token = _find_token(resp.json())
        if not token:
            raise VoiceLinkError(resp.status_code, "login response contained no token")
        self._token = token
        return token

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in (1, 2):
            if self._token is None:
                async with self._lock:
                    if self._token is None:
                        await self.login()
            headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
            resp = await self._http.request(method, path, headers=headers, **kwargs)
            if resp.status_code == 401 and attempt == 1:
                self._token = None  # expired token: log in again once
                continue
            return resp
        return resp

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = await self._request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise VoiceLinkError(resp.status_code, resp.text[:300])
        return resp.json() if resp.content else {}

    # ---- calls
    async def add_lead(self, did_number: str, customer_number: str, custom_parameters: dict[str, Any],
                       websocket_url: str | None = None, webhook_url: str | None = None,
                       country_code: str = "91") -> Any:
        body: dict[str, Any] = {
            "did_number": did_number,
            "customer_number": "".join(c for c in customer_number if c.isdigit())[-10:],
            "country_code": country_code,
            "custom_parameters": json.dumps(custom_parameters, ensure_ascii=False),
        }
        if websocket_url:
            body["websocket_url"] = websocket_url
        if webhook_url:
            body["webhook_url"] = webhook_url
        return await self._json("POST", "/v1/add_lead", json=body)

    async def call_details(self, call_id: str) -> Any:
        return await self._json("GET", "/v1/call-log/details", params={"call_id": call_id})

    async def pause_queue(self, client_id: int) -> Any:
        return await self._json("POST", f"/v1/websocket-management/pause/{client_id}")

    async def resume_queue(self, client_id: int) -> Any:
        return await self._json("POST", f"/v1/websocket-management/resume/{client_id}")

    # ---- setup (app/devtools/voicelink_setup.py)
    async def list_websocket_bots(self, search: str | None = None) -> Any:
        return await self._json("GET", "/v1/websocket-bot/list", params={"search": search} if search else None)

    async def create_websocket_bot(self, bot_name: str, websocket_url: str, client_id: int, webhook_url: str | None,
                                   audio_format: str = "ulaw", noise_cancel: bool = False) -> Any:
        body = {"bot_name": bot_name, "websocket_url": websocket_url, "client_id": client_id, "status": 1,
                "audio_format": audio_format, "noise_cancel": int(noise_cancel)}
        if webhook_url:
            body["webhook_url"] = webhook_url
        return await self._json("POST", "/v1/websocket-bot/create", json=body)

    async def update_websocket_bot(self, bot_id: int, bot_name: str, websocket_url: str, webhook_url: str | None,
                                   audio_format: str = "ulaw", noise_cancel: bool = False) -> Any:
        body = {"bot_name": bot_name, "websocket_url": websocket_url, "status": 1, "audio_format": audio_format,
                "noise_cancel": int(noise_cancel)}
        if webhook_url:
            body["webhook_url"] = webhook_url
        return await self._json("POST", f"/v1/websocket-bot/update/{bot_id}", json=body)

    async def create_call_routing(self, did_number: str, inbound_bot_id: int, outbound_bot_id: int) -> Any:
        body = {"did_number": did_number, "for_inbound_call": 3, "for_outbound_call": 3,
                "inbound_websocket_bot_id": inbound_bot_id, "outbound_websocket_bot_id": outbound_bot_id, "status": 1}
        return await self._json("POST", "/v1/call-routing/create", json=body)

    async def list_call_routings(self) -> Any:
        return await self._json("GET", "/v1/call-routing/list")

    async def update_call_routing(self, routing_id: int, inbound_bot_id: int, outbound_bot_id: int) -> Any:
        body = {"for_inbound_call": 3, "for_outbound_call": 3, "inbound_websocket_bot_id": inbound_bot_id,
                "outbound_websocket_bot_id": outbound_bot_id, "status": 1}
        return await self._json("POST", f"/v1/call-routing/update/{routing_id}", json=body)

    async def create_time_group(self, group_name: str, client_ids: list[int], start: str, end: str, days: int = 7) -> Any:
        schedule = [{"is_24h": 0, "working": 1, "start": start, "end": end} for _ in range(days)]
        return await self._json("POST", "/v1/websocket-time-group/create",
                                json={"group_name": group_name, "status": 1, "client_ids": client_ids, "schedule": schedule})

    async def aclose(self) -> None:
        await self._http.aclose()


# --------------------------------------------------------------------------- media websocket

def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if data.get(key) not in (None, ""):
            return data[key]
    return None


def _custom(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def _shape(data: Any) -> Any:
    """Keys and nesting only, never values (values can contain phone numbers)."""
    if isinstance(data, dict):
        return {k: _shape(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_shape(data[0])] if data else []
    return type(data).__name__


def parse_start(data: dict[str, Any]) -> CallStart | None:
    src = data.get("start") if isinstance(data.get("start"), dict) else data
    event = str(_first(data, "event", "type") or "").lower()
    call_id = _first(src, "call_id", "callId", "call_sid", "callSid", "unique_id", "uuid")
    if event not in START_EVENTS and call_id is None:
        return None
    custom = _custom(_first(src, "custom_parameters", "customParameters", "custom"))
    direction = str(_first(src, "direction") or _first(custom, "direction") or "inbound").lower()
    return CallStart(
        call_id=str(call_id or uuid.uuid4().hex),
        stream_id=str(_first(src, "stream_sid", "streamSid", "stream_id", "streamId") or _first(data, "stream_sid", "streamSid") or ""),
        from_number=_first(src, "from", "caller", "caller_id", "callerId", "customer_number", "ani"),
        to_number=_first(src, "to", "did", "did_number", "dnis", "called"),
        direction="outbound" if "out" in direction else "inbound",
        custom=custom,
    )


def media_format_of(data: dict[str, Any]) -> dict[str, Any] | None:
    src = data.get("start") if isinstance(data.get("start"), dict) else data
    mf = _first(src, "media_format", "mediaFormat")
    return mf if isinstance(mf, dict) else None


class DebugAudio:
    """Dev-only raw capture of wire audio for diagnosing format problems. Enable with VOICE_LINK_DEBUG_AUDIO."""

    def __init__(self, directory: Path, call_id: str, max_bytes: int = 5_000_000):
        directory.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in call_id if c.isalnum() or c in "-_")[:64] or "call"
        self.inbound = open(directory / f"{safe}.in.raw", "wb")
        self.outbound = open(directory / f"{safe}.out.raw", "wb")
        self.meta_path = directory / f"{safe}.meta.json"
        self.max_bytes = max_bytes

    def write(self, fh, data: bytes) -> None:
        if not fh.closed and fh.tell() < self.max_bytes:
            fh.write(data)

    def meta(self, **values: Any) -> None:
        self.meta_path.write_text(json.dumps(values, indent=1, default=str))

    def close(self) -> None:
        self.inbound.close()
        self.outbound.close()


class VoiceLinkTransport:
    def __init__(self, websocket: WebSocket, start: CallStart, capture: int = 0, early_audio: list[bytes] | None = None,
                 wire: WireFormat | None = None, default_format: str = "ulaw", out_chunk_ms: int = 40,
                 media_format: dict[str, Any] | None = None, debug_dir: Path | None = None):
        self.ws = websocket
        self.start = start
        self.dtmf: list[str] = []
        self.closed = False
        self.binary_audio = bool(early_audio)
        self.media_format = media_format
        self.wire = wire
        self._default = WireFormat.from_bot_setting(default_format)
        rate = int(str((media_format or {}).get("sample_rate") or 8000)) if str((media_format or {}).get("sample_rate") or "8000").isdigit() else 8000
        self._detector = None if wire else CodecDetector(sample_rate=rate if rate in (8000, 16000) else 8000)
        self._format_ready = asyncio.Event()
        if wire:
            self._format_ready.set()
        self._pending_in: list[bytes] = list(early_audio or [])
        self._capture = capture
        self._clear_warned = False
        self._media_logged = False
        self._out_chunk_ms = out_chunk_ms
        self._out_buffer = b""
        self._flush_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._debug = DebugAudio(debug_dir, start.call_id) if debug_dir else None
        if early_audio and wire is None:
            for chunk in early_audio:
                self._detector.feed(chunk)

    @classmethod
    async def accept(cls, websocket: WebSocket, capture: int = 20, start_timeout_s: float = 5.0,
                     default_format: str = "ulaw", out_chunk_ms: int = 40,
                     debug_dir: Path | None = None) -> "VoiceLinkTransport":
        await websocket.accept()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + start_timeout_s
        early: list[bytes] = []
        while loop.time() < deadline:
            try:
                message = await asyncio.wait_for(websocket.receive(), deadline - loop.time())
            except asyncio.TimeoutError:
                break
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes"):
                early.append(message["bytes"])
                if len(early) > 5:
                    break  # audio is flowing without a start event
                continue
            try:
                data = json.loads(message.get("text") or "{}")
            except ValueError:
                continue
            if capture:
                log.info("VoiceLink message shape: %s", json.dumps(_shape(data)))
                capture -= 1
            if isinstance(data, dict) and (start := parse_start(data)):
                mf = media_format_of(data)
                wire = format_from_media_format(mf)
                log.info("VoiceLink media_format encoding=%r sample_rate=%r -> %s", (mf or {}).get("encoding"),
                         (mf or {}).get("sample_rate"), wire or "detect from audio")
                return cls(websocket, start, capture, early, wire=wire, default_format=default_format,
                           out_chunk_ms=out_chunk_ms, media_format=mf, debug_dir=debug_dir)
        log.warning("VoiceLink: no recognisable start event; continuing with a generated call id")
        start = CallStart(call_id=uuid.uuid4().hex, stream_id="", from_number=None, to_number=None, direction="inbound")
        return cls(websocket, start, capture, early, default_format=default_format, out_chunk_ms=out_chunk_ms,
                   debug_dir=debug_dir)

    # ---- inbound
    def _decide(self, wire: WireFormat, reason: str) -> None:
        self.wire = wire
        self._format_ready.set()
        log.info("VoiceLink wire audio format: %s (%s)", wire, reason)
        if self._debug:
            self._debug.meta(media_format=self.media_format, wire=str(wire), reason=reason)

    def _inbound(self, raw: bytes) -> list[bytes]:
        if self._debug:
            self._debug.write(self._debug.inbound, raw)
        if self.wire is None:
            self._pending_in.append(raw)
            detected = self._detector.feed(raw) if self._detector else None
            if detected is None and (self._detector is None or self._detector.bytes_seen < 16000):
                return []
            self._decide(detected or self._default, self._detector.reason if detected else "undetectable: bot default")
            pending, self._pending_in = self._pending_in, []
            return [self.wire.to_internal(p) for p in pending]
        return [self.wire.to_internal(raw)]

    def _drain_pending(self) -> list[bytes]:
        if self.wire is None and self._pending_in:
            self._decide(self._default, "stream ended before detection")
        pending, self._pending_in = self._pending_in, []
        return [self.wire.to_internal(p) for p in pending] if pending else []

    async def audio_frames(self) -> AsyncIterator[bytes]:
        try:
            while True:
                message = await self.ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes"):
                    self.binary_audio = True
                    for frame in self._inbound(message["bytes"]):
                        yield frame
                    continue
                try:
                    data = json.loads(message.get("text") or "{}")
                except ValueError:
                    continue
                event = str(_first(data, "event", "type") or "").lower()
                if event == "media":
                    media = data.get("media") if isinstance(data.get("media"), dict) else data
                    payload = _first(media, "payload", "audio", "data", "chunk")
                    if payload:
                        raw = base64.b64decode(payload)
                        if not self._media_logged:
                            self._media_logged = True
                            log.info("VoiceLink media message shape: %s, payload bytes: %d", json.dumps(_shape(data)), len(raw))
                        for frame in self._inbound(raw):
                            yield frame
                    continue
                if self._capture:
                    log.info("VoiceLink message shape: %s", json.dumps(_shape(data)))
                    self._capture -= 1
                if event == "dtmf":
                    dtmf = data.get("dtmf") if isinstance(data.get("dtmf"), dict) else data
                    self.dtmf.append(str(_first(dtmf, "digit", "dtmf") or ""))
                elif event in STOP_EVENTS:
                    break
            for frame in self._drain_pending():
                yield frame
        finally:
            self.closed = True
            if self._flush_task:
                self._flush_task.cancel()
            if self._debug:
                self._debug.close()

    # ---- outbound
    async def _wire_format(self) -> WireFormat:
        if self.wire is None:
            try:
                await asyncio.wait_for(self._format_ready.wait(), 0.6)
            except asyncio.TimeoutError:
                if self.wire is None:
                    self._decide(self._default, "no inbound audio yet: bot default")
        return self.wire  # type: ignore[return-value]

    async def _send_wire(self, data: bytes) -> None:
        if self.closed or not data:
            return
        if self._debug:
            self._debug.write(self._debug.outbound, data)
        try:
            if self.binary_audio:
                await self.ws.send_bytes(data)
            else:
                await self.ws.send_text(json.dumps({"event": "media", "stream_sid": self.start.stream_id,
                                                    "media": {"payload": base64.b64encode(data).decode()}}))
        except RuntimeError:
            self.closed = True

    async def send_audio(self, mulaw_8k: bytes) -> None:
        if self.closed:
            return
        wire = await self._wire_format()
        chunk = wire.bytes_for_ms(self._out_chunk_ms)
        async with self._send_lock:
            self._out_buffer += wire.from_internal(mulaw_8k)
            while len(self._out_buffer) >= chunk:
                data, self._out_buffer = self._out_buffer[:chunk], self._out_buffer[chunk:]
                await self._send_wire(data)
        if self._out_buffer:
            if self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await asyncio.sleep(self._out_chunk_ms / 1000)
        wire = self.wire
        async with self._send_lock:
            if not self._out_buffer or wire is None:
                return
            frame = wire.bytes_for_ms(20)
            remainder = len(self._out_buffer) % frame
            data = self._out_buffer + (wire.silence(frame - remainder) if remainder else b"")
            self._out_buffer = b""
            await self._send_wire(data)

    async def clear_audio(self) -> None:
        self._out_buffer = b""
        if self._flush_task:
            self._flush_task.cancel()
        if self.closed:
            return
        if self.binary_audio:
            if not self._clear_warned:
                log.warning("VoiceLink binary audio mode: no documented clear message; barge-in cannot flush buffered audio")
                self._clear_warned = True
            return
        try:
            await self.ws.send_text(json.dumps({"event": "clear", "stream_sid": self.start.stream_id}))
        except RuntimeError:
            self.closed = True

    async def hangup(self) -> None:
        # No hangup endpoint exists in the REST spec; closing the media socket ends the bot leg.
        if not self.closed:
            self.closed = True
            try:
                await self.ws.close()
            except RuntimeError:
                pass
