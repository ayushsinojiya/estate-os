"""Outside TRAI hours only allow-listed test numbers are dialled; do-not-call always applies."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.config import Settings
from app.domain.real_estate import plugin as plugin_mod
from app.outbound.registry import OutboundRecord

LATE = datetime(2026, 10, 3, 23, 46, tzinfo=ZoneInfo("Asia/Kolkata"))
NOON = datetime(2026, 10, 3, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def _plugin(monkeypatch, now, allowlist="", dnc=False):
    monkeypatch.setattr(plugin_mod, "now_ist", lambda: now)
    settings = Settings(crm_mode="mock", test_phone_allowlist=allowlist)
    services = SimpleNamespace(settings=settings, outbox=SimpleNamespace(register=lambda *a: None),
                               dialer=SimpleNamespace(), registry=SimpleNamespace(suppress=lambda *a: None))
    p = plugin_mod.RealEstatePlugin(services)

    async def check_dnc(phone):
        return dnc
    p.crm.check_dnc = check_dnc
    return p


def _dial(p, phone):
    return asyncio.run(p.may_dial(OutboundRecord("r1", phone)))


def test_late_calls_are_refused_for_everyone_else(monkeypatch):
    p = _plugin(monkeypatch, LATE, allowlist="9328396344")
    assert _dial(p, "+919800000001") == (False, "OUTSIDE_CALLING_HOURS")


def test_an_allow_listed_test_number_may_be_called_late_in_any_format(monkeypatch):
    p = _plugin(monkeypatch, LATE, allowlist="+91 93283 96344, 9800000002")
    assert _dial(p, "+919328396344") == (True, None)
    assert _dial(p, "09800000002") == (True, None)


def test_do_not_call_still_wins_for_a_test_number(monkeypatch):
    p = _plugin(monkeypatch, LATE, allowlist="9328396344", dnc=True)
    assert _dial(p, "+919328396344") == (False, "DO_NOT_CALL")


def test_daytime_calls_are_unaffected(monkeypatch):
    assert _dial(_plugin(monkeypatch, NOON), "+919800000001") == (True, None)
