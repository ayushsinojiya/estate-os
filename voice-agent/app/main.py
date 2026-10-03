"""FastAPI service: VoiceLink media websocket, webhook, health, plus the domain's own routes.

Run: uvicorn app.main:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket

from app.config import cost_prices, Settings, get_settings
from app.conversation.caller_audio import AudioCallerInput
from app.conversation.session import CallSession
from app.conversation.speech import AudioSpeechOutput
from app.domain.base import CallInfo
from app.lang.languages import LANGS
from app.llm.base import LLMProvider
from app.observability.logging import configure as configure_logging
from app.resilience.probes import LLMProbe
from app.telephony.voicelink import VoiceLinkTransport
from app.wiring import Container, PluginFactory, build_container, domain_routes

log = logging.getLogger("voice-agent")


async def _minute_ticker(c: Container) -> None:
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(60)
        now = loop.time()
        c.llm_leg.tick(now)
        c.stt_leg.tick(now)


def _share_probe(c: Container, usage) -> None:
    """A probe runs because calls are live: its cost is shared equally between them."""
    sessions = list(c.active_calls.values())
    for session in sessions:
        share = 1 / len(sessions)
        session.cost.add_request("probe", share)
        if usage is not None:
            session.cost.add_usage("probe", usage, share)


async def _finish(c: Container, session: CallSession) -> None:
    record = session.record()
    try:
        await session.conversation.finish(record)
    except Exception:  # noqa: BLE001 - post-call work is retried by the outbox, never by the caller
        log.exception("call %s: post-call processing failed", session.info.call_id)
    # After post-call work, so its model usage is included.
    cost = record.cost.summary(cost_prices(c.settings))
    log.info("call %s cost: %s", session.info.call_id, json.dumps(cost, ensure_ascii=False))
    for entry in c.recent_metrics:
        if entry.get("call_id") == session.info.call_id:
            entry["cost"] = cost


async def handle_call(c: Container, websocket: WebSocket) -> None:
    s = c.settings
    transport = await VoiceLinkTransport.accept(
        websocket, capture=s.voice_link_capture_messages,
        default_format=s.voice_link_default_audio_format,
        out_chunk_ms=s.voice_link_out_chunk_ms,
        debug_dir=s.audio_cache_dir / "debug_audio" if s.voice_link_debug_audio else None)
    start = transport.start
    if len(c.active_calls) >= s.max_concurrent_calls:
        log.warning("rejecting call %s: at capacity", start.call_id)
        await transport.hangup()
        return

    custom = start.custom
    phone = start.from_number if start.direction == "inbound" else start.to_number
    language = custom.get("language") if custom.get("language") in LANGS else None
    info = CallInfo(call_id=start.call_id or uuid.uuid4().hex, direction=start.direction,
                    caller_phone=phone, language_hint=language, custom=dict(custom))
    c.dialer.connected(info.call_id, info.custom)
    c.metrics.inc(f"calls_{info.direction}")

    primary_stt, fallback_stt = c.stt_factories(language or s.default_inbound_language)
    caller = AudioCallerInput(primary_stt, fallback_stt, stt_leg=c.stt_leg,
                              flush_after_s=s.stt_flush_after_ms / 1000)
    tts = c.new_tts()
    if hasattr(tts.primary, "warm"):
        tts.primary.warm()  # open the socket now so the first reply skips the connect cost
    speech = AudioSpeechOutput(transport, tts, c.phrase_cache,
                               on_speaking=caller.set_agent_speaking,
                               output_gain=s.tts_output_gain)
    conversation = c.plugin.conversation(info)
    session = CallSession(c.session_deps(), info, caller, speech, transport.hangup, conversation)
    c.active_calls[info.call_id] = session

    async def pump() -> None:
        async for frame in transport.audio_frames():
            await caller.push_audio(frame)
        await session.on_caller_hangup()

    await caller.start()
    pump_task = asyncio.create_task(pump())
    try:
        metrics = await session.run()
        summary = metrics.summary()
        c.recent_metrics.append({"call_id": info.call_id, **summary})
        c.dialer.finished(info.call_id, summary)
        c.metrics.inc(f"call_end_{summary['end_reason']}")
        log.info("call %s ended: %s", info.call_id, summary)
    finally:
        pump_task.cancel()
        c.active_calls.pop(info.call_id, None)
        await caller.close()
        await tts.close()
        c.track(asyncio.create_task(_finish(c, session)))


def create_app(settings: Settings | None = None, plugin_factory: PluginFactory | None = None,
               llm: LLMProvider | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        c = build_container(settings, plugin_factory, llm)
        app.state.c = c
        await c.plugin.start()
        # Bring cached phrase audio into memory before answering: after this the speech path
        # never reads from disk, and a warm cache survives a restart.
        log.info("phrase cache resident: %d clips", await c.phrase_cache.preload())
        tasks = [asyncio.create_task(_minute_ticker(c)),
                 asyncio.create_task(LLMProbe(c.router.primary, c.llm_leg, c.governor,
                                              settings.llm_probe_interval_s,
                                              active_calls=lambda: len(c.active_calls),
                                              messages=c.plugin.probe_messages,
                                              on_usage=lambda u: _share_probe(c, u)).loop()),
                 asyncio.create_task(c.dialer.run()),
                 asyncio.create_task(c.outbox.run())]
        if settings.provider_mode == "live":
            tasks.append(asyncio.create_task(c.phrase_cache.warm(c.new_tts().primary)))
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if c.background:
            await asyncio.wait(list(c.background), timeout=5)
        await c.plugin.stop()
        c.registry.close()
        c.outbox.close()

    app = FastAPI(title="Real-estate voice agent", lifespan=lifespan)

    def container() -> Container:
        return app.state.c

    def admin(authorization: str = Header(default="")) -> None:
        if settings.admin_api_token and authorization != f"Bearer {settings.admin_api_token}":
            raise HTTPException(401, "unauthorised")

    @app.get("/healthz")
    async def healthz(c: Container = Depends(container)) -> dict:
        from app.outbound.registry import CONNECTED, DIALING, QUEUED

        return {"status": "ok", "mode": settings.provider_mode,
                "active_calls": len(c.active_calls),
                "llm_leg": c.llm_leg.state, "stt_leg": c.stt_leg.state,
                "governor_used_per_min": c.governor.used(),
                "governor_limit_per_min": c.governor.limit,
                "outbound": {"queued": c.registry.count(QUEUED), "dialing": c.registry.count(DIALING),
                             "connected": c.registry.count(CONNECTED),
                             "paused": c.routing.outbound_paused},
                "outbox": c.outbox.counts(),
                c.plugin.name: c.plugin.health()}

    @app.get("/metrics", dependencies=[Depends(admin)])
    async def metrics(c: Container = Depends(container)) -> dict:
        return c.metrics.snapshot()

    @app.websocket("/telephony/voicelink/ws")
    async def voicelink_ws(websocket: WebSocket) -> None:
        await handle_call(app.state.c, websocket)

    @app.post("/telephony/voicelink/webhook")
    async def voicelink_webhook(request: Request, token: str = "",
                                c: Container = Depends(container)) -> dict:
        if settings.voice_link_webhook_token and token != settings.voice_link_webhook_token:
            raise HTTPException(401, "unauthorised")
        try:
            payload: Any = await request.json()
        except ValueError:
            payload = {"raw": (await request.body()).decode("utf-8", "replace")[:2000]}
        c.recent_webhooks.append(payload)
        record = c.dialer.on_webhook(payload)
        hook = getattr(c.plugin, "on_outbound_update", None)
        if record is not None and hook is not None:
            await hook(record)
        return {"ok": True}

    @app.get("/calls/recent", dependencies=[Depends(admin)])
    async def recent(c: Container = Depends(container)) -> list:
        return list(c.recent_metrics)

    # Domain routes (for real estate: the CRM's outbound-call and call-details contract).
    app.include_router(domain_routes(container, admin))
    return app


app = create_app()
