"""The outbound dialler, the call registry, the suppression cache and the retry outbox."""

import asyncio

from app.outbound.dialer import OutboundDialer
from app.outbound.registry import (CONNECTED, DIALING, NO_ANSWER, QUEUED, REFUSED, SIMULATED,
                                   CallRegistry)
from app.outbox.outbox import DEAD, DELIVERED, PENDING, Outbox, PermanentFailure


class FakeQueue:
    def __init__(self, fail=False):
        self.leads = []
        self.fail = fail

    async def add_lead(self, did, phone, custom, websocket_url=None, webhook_url=None, country_code="91"):
        if self.fail:
            raise RuntimeError("provider down")
        self.leads.append((phone, custom))
        return {"id": len(self.leads)}

    async def pause_queue(self, client_id):
        return None

    async def resume_queue(self, client_id):
        return None


def test_submit_is_idempotent_and_dials_once(tmp_path):
    registry = CallRegistry(tmp_path / "calls.sqlite")
    queue = FakeQueue()
    dialer = OutboundDialer(registry, queue, did_number="02000000000")

    async def scenario():
        a = await dialer.submit("req-1", "+919800000001", {"callType": "CALLBACK"})
        b = await dialer.submit("req-1", "+919800000001", {"callType": "CALLBACK"})
        assert a.request_id == b.request_id and a.status == QUEUED
        assert await dialer.dial_once() == 1
        assert await dialer.dial_once() == 0

    asyncio.run(scenario())
    assert len(queue.leads) == 1
    assert queue.leads[0][1]["request_id"] == "req-1"
    assert registry.get("req-1").status == DIALING


def test_a_suppressed_number_is_refused_without_dialling(tmp_path):
    registry = CallRegistry(tmp_path / "calls.sqlite")
    registry.suppress("+91 98000 00002", "caller asked")
    queue = FakeQueue()
    dialer = OutboundDialer(registry, queue)
    record = asyncio.run(dialer.submit("req-2", "9800000002", {}))
    assert record.status == REFUSED and record.reason == "DO_NOT_CALL"
    assert queue.leads == []


def test_the_domain_can_refuse_a_dial(tmp_path):
    registry = CallRegistry(tmp_path / "calls.sqlite")

    async def outside_hours(_record):
        return False, "OUTSIDE_CALLING_HOURS"

    dialer = OutboundDialer(registry, FakeQueue(), may_dial=outside_hours)

    async def scenario():
        await dialer.submit("req-3", "9800000003", {})
        await dialer.dial_once()

    asyncio.run(scenario())
    assert registry.get("req-3").reason == "OUTSIDE_CALLING_HOURS"


def test_fake_mode_never_dials(tmp_path):
    registry = CallRegistry(tmp_path / "calls.sqlite")
    dialer = OutboundDialer(registry, None)

    async def scenario():
        await dialer.submit("req-4", "9800000004", {})
        await dialer.dial_once()

    asyncio.run(scenario())
    assert registry.get("req-4").status == SIMULATED


def test_connection_and_unanswered_webhook_update_the_request(tmp_path):
    registry = CallRegistry(tmp_path / "calls.sqlite")
    dialer = OutboundDialer(registry, FakeQueue())

    async def scenario():
        await dialer.submit("req-5", "9800000005", {})
        await dialer.submit("req-6", "9800000006", {})
        await dialer.dial_once()

    asyncio.run(scenario())
    assert dialer.connected("call-5", {"request_id": "req-5"}).status == CONNECTED
    dialer.on_webhook({"event": "call.ended", "call": {"status": "no-answer",
                                                         "custom_parameters": '{"request_id": "req-6"}'}})
    assert registry.get("req-6").status == NO_ANSWER


def test_provider_failure_retries_then_gives_up(tmp_path):
    registry = CallRegistry(tmp_path / "calls.sqlite")
    dialer = OutboundDialer(registry, FakeQueue(fail=True), max_attempts=2)

    async def scenario():
        await dialer.submit("req-7", "9800000007", {})
        await dialer.dial_once()
        assert registry.get("req-7").status == QUEUED
        await dialer.dial_once()

    asyncio.run(scenario())
    assert registry.get("req-7").status == "FAILED"


def test_outbox_delivers_once_and_retries_with_backoff(tmp_path):
    now = [1000.0]
    outbox = Outbox(tmp_path / "outbox.sqlite", base_delay_s=10, clock=lambda: now[0])
    attempts = []

    async def flaky(payload):
        attempts.append(payload)
        if len(attempts) == 1:
            raise RuntimeError("crm unavailable")

    outbox.register("ingest", flaky)
    assert outbox.enqueue("ingest", "call-1", {"callId": "call-1"})
    assert not outbox.enqueue("ingest", "call-1", {"callId": "call-1"})  # same key: no-op

    asyncio.run(outbox.deliver_due())
    assert outbox.item("call-1")["status"] == PENDING
    asyncio.run(outbox.deliver_due())  # not due yet
    assert len(attempts) == 1
    now[0] += 11
    asyncio.run(outbox.deliver_due())
    assert outbox.item("call-1")["status"] == DELIVERED
    assert len(attempts) == 2


def test_outbox_stops_on_a_permanent_rejection(tmp_path):
    outbox = Outbox(tmp_path / "outbox.sqlite")

    async def reject(payload):
        raise PermanentFailure("400 bad payload")

    outbox.register("ingest", reject)
    outbox.enqueue("ingest", "call-2", {})
    asyncio.run(outbox.deliver_due())
    assert outbox.item("call-2")["status"] == DEAD
