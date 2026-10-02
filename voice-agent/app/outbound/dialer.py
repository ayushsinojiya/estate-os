"""Outbound dialling: a paced queue in front of the telephony provider's own dialer.

VoiceLink places outbound calls itself once a lead is added to its queue (POST /v1/add_lead). This
module decides *whether* and *when* to hand a request over: it refuses suppressed numbers, asks
the domain whether the call may be placed now (calling hours, consent), paces submissions, caps
the number of calls in flight, and pauses entirely while the STT leg is degraded.

With no provider configured (PROVIDER_MODE=fake) a request is recorded as SIMULATED: nothing is
dialled, which keeps fake mode honest.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from app.outbound.registry import (COMPLETED, CONNECTED, DIALING, FAILED, NO_ANSWER, QUEUED, REFUSED,
                                   SIMULATED, CallRegistry, OutboundRecord)
from app.telephony.base import OutboundQueue

log = logging.getLogger(__name__)

MayDial = Callable[[OutboundRecord], Awaitable[tuple[bool, str | None]]]


async def _always(_record: OutboundRecord) -> tuple[bool, str | None]:
    return True, None


# Webhook events that mean the call never reached a person.
_UNANSWERED = {"no-answer", "no_answer", "noanswer", "busy", "failed", "not_answered", "unanswered",
               "cancel", "cancelled", "rejected"}


class OutboundDialer:
    def __init__(self, registry: CallRegistry, queue: OutboundQueue | None, *, did_number: str = "",
                 websocket_url: str | None = None, webhook_url: str | None = None,
                 may_dial: MayDial = _always, paused: Callable[[], bool] = lambda: False,
                 max_in_flight: int = 5, min_interval_s: float = 2.0, max_attempts: int = 2,
                 dial_timeout_s: float = 180.0):
        self.registry = registry
        self.queue = queue
        self.did_number = did_number
        self.websocket_url = websocket_url
        self.webhook_url = webhook_url
        self.may_dial = may_dial
        self.paused = paused
        self.max_in_flight = max_in_flight
        self.min_interval_s = min_interval_s
        self.max_attempts = max_attempts
        self.dial_timeout_s = dial_timeout_s
        self.wake = asyncio.Event()

    # ---- intake

    async def submit(self, request_id: str, phone: str, custom: dict[str, Any]) -> OutboundRecord:
        """Record a request (idempotent on request_id) and wake the dialler."""
        existing = self.registry.get(request_id)
        if existing is not None:
            return existing
        if self.registry.is_suppressed(phone):
            return self.registry.add(OutboundRecord(request_id, phone, REFUSED, custom,
                                                    reason="DO_NOT_CALL"))
        record = self.registry.add(OutboundRecord(request_id, phone, QUEUED, custom))
        self.wake.set()
        return record

    # ---- dialling

    def in_flight(self) -> int:
        return self.registry.count(DIALING) + self.registry.count(CONNECTED)

    def _expire_stale(self) -> None:
        cutoff = time.time() - self.dial_timeout_s
        for record in self.registry.with_status(DIALING, older_than=cutoff):
            log.info("outbound %s: no answer within %.0fs", record.request_id, self.dial_timeout_s)
            self.registry.update(record.request_id, status=NO_ANSWER, reason="NO_ANSWER")

    async def dial_once(self) -> int:
        """Hand queued requests to the provider. Returns how many were placed (or simulated)."""
        self._expire_stale()
        if self.paused():
            return 0
        placed = 0
        for record in self.registry.queued(limit=self.max_in_flight):
            if self.queue is not None and self.in_flight() >= self.max_in_flight:
                break
            if self.registry.is_suppressed(record.phone):
                self.registry.update(record.request_id, status=REFUSED, reason="DO_NOT_CALL")
                continue
            allowed, reason = await self.may_dial(record)
            if not allowed:
                self.registry.update(record.request_id, status=REFUSED, reason=reason or "NOT_ALLOWED")
                continue
            if self.queue is None:
                self.registry.update(record.request_id, status=SIMULATED, reason="FAKE_PROVIDER",
                                     attempt=True)
                placed += 1
                continue
            try:
                # The provider gets only the request id (and a language hint); the full request,
                # context included, stays in the registry and is looked up when the call connects.
                params = {"request_id": record.request_id}
                if record.custom.get("language"):
                    params["language"] = record.custom["language"]
                result = await self.queue.add_lead(
                    self.did_number, record.phone, params,
                    websocket_url=self.websocket_url, webhook_url=self.webhook_url)
            except Exception as exc:  # noqa: BLE001 - provider errors are recorded, never raised
                attempts = record.attempts + 1
                status = FAILED if attempts >= self.max_attempts else QUEUED
                log.warning("outbound %s: provider rejected (%r), attempt %d", record.request_id,
                            exc, attempts)
                self.registry.update(record.request_id, status=status, reason="PROVIDER_ERROR",
                                     attempt=True)
                continue
            self.registry.update(record.request_id, status=DIALING, attempt=True,
                                 details={"provider": result if isinstance(result, dict) else {}})
            placed += 1
        return placed

    async def run(self) -> None:
        while True:
            try:
                await self.dial_once()
            except Exception:  # noqa: BLE001 - the dialler must outlive any one bad request
                log.exception("outbound dialler error")
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), self.min_interval_s)
            except asyncio.TimeoutError:
                pass

    # ---- call lifecycle

    def connected(self, call_id: str, custom: dict[str, Any]) -> OutboundRecord | None:
        request_id = str(custom.get("request_id") or "")
        if not request_id or self.registry.get(request_id) is None:
            return None
        return self.registry.update(request_id, status=CONNECTED, call_id=call_id)

    def finished(self, call_id: str, details: dict[str, Any]) -> OutboundRecord | None:
        record = self.registry.by_call(call_id)
        if record is None:
            return None
        return self.registry.update(record.request_id, status=COMPLETED, details=details)

    def on_webhook(self, payload: Any) -> OutboundRecord | None:
        """Map a provider status webhook onto the request it belongs to."""
        if not isinstance(payload, dict):
            return None
        call = payload.get("call") if isinstance(payload.get("call"), dict) else payload
        event = str(payload.get("event") or payload.get("type") or "").lower()
        status = str(call.get("status") or call.get("call_status") or "").lower()
        custom = call.get("custom_parameters") or payload.get("custom_parameters") or {}
        if isinstance(custom, str):
            import json
            try:
                custom = json.loads(custom)
            except ValueError:
                custom = {}
        record = None
        if isinstance(custom, dict) and custom.get("request_id"):
            record = self.registry.get(str(custom["request_id"]))
        if record is None and call.get("id"):
            record = self.registry.by_call(str(call["id"]))
        if record is None:
            return None
        if status in _UNANSWERED or (event.endswith("ended") and record.status == DIALING):
            return self.registry.update(record.request_id, status=NO_ANSWER,
                                        reason=status.upper() or "NO_ANSWER")
        return record
