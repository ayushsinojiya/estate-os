"""Rate governor, degradation monitors and LLM primary/fallback routing."""

import asyncio

import pytest

from app.llm.base import ProviderUnavailable
from app.llm.fake import ScriptedLLM, say
from app.llm.router import AllProvidersFailed, LLMRoute, LLMRouter
from app.resilience.degradation import LegMonitor, LegState, LegThresholds, RoutingPolicy
from app.resilience.rate_governor import Priority, RateGovernor


def test_governor_keeps_headroom_for_live_turns():
    now = [0.0]
    gov = RateGovernor(10, clock=lambda: now[0], probe_ceiling=0.5)
    assert all(gov.try_acquire(Priority.PROBE) for _ in range(5))
    assert not gov.try_acquire(Priority.PROBE)
    assert all(gov.try_acquire(Priority.LIVE) for _ in range(5))
    assert not gov.try_acquire(Priority.LIVE)
    now[0] = 61
    assert gov.try_acquire(Priority.LIVE)


def test_a_slow_leg_trips_after_consecutive_minutes_and_recovers():
    leg = LegMonitor("llm", LegThresholds(trip_p95_ms=1000, recover_p95_ms=700, trip_minutes=2,
                                          recover_minutes=2, min_samples=3, window_s=30))
    t = 0.0
    for minute in range(2):
        for _ in range(3):
            leg.record(t, latency_ms=1500)
        leg.tick(t)
        t += 60
    assert leg.state == LegState.DEGRADED
    for minute in range(2):
        for _ in range(3):
            leg.record(t, latency_ms=100)
        leg.tick(t)
        t += 60
    assert leg.state == LegState.HEALTHY


def test_degraded_stt_without_a_proven_fallback_pauses_outbound():
    llm = LegMonitor("llm", LegThresholds(trip_p95_ms=1, recover_p95_ms=1))
    stt = LegMonitor("stt", LegThresholds(trip_p95_ms=1, recover_p95_ms=1))
    policy = RoutingPolicy(llm, stt, nova3_floor_passed=False)
    assert not policy.outbound_paused
    stt.state = LegState.DEGRADED
    assert policy.outbound_paused


def _collect(router, route):
    async def run():
        return [e async for e in router.stream(route, lambda _p: [], [])]
    return asyncio.run(run())


def test_primary_failure_moves_the_call_to_the_fallback():
    router = LLMRouter(ScriptedLLM(error=ProviderUnavailable("down"), name="primary"),
                       ScriptedLLM([say("from fallback")], name="fallback"))
    route = LLMRoute()
    events = _collect(router, route)
    assert route.use_fallback and route.provider_used == "fallback"
    assert events[0].text == "from fallback"


def test_first_token_timeout_counts_as_a_hard_failure():
    router = LLMRouter(ScriptedLLM([say("late")], first_event_delay_s=0.2, name="primary"),
                       ScriptedLLM([say("quick")], name="fallback"), first_token_timeout_s=0.05)
    route = LLMRoute()
    _collect(router, route)
    assert route.reason == "first_token_timeout"


def test_no_fallback_raises_for_the_session_to_handle():
    router = LLMRouter(ScriptedLLM(error=ProviderUnavailable("down")), None)
    with pytest.raises(AllProvidersFailed):
        _collect(router, LLMRoute())
