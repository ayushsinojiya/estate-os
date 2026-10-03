"""Slow-degradation detection and new-call routing (spec section 30).

Each leg (LLM, STT) trips independently on a rolling p95 (or request error rate) sustained for
N consecutive minutes, recovers after M consecutive good minutes, and pages on-call at an
alert threshold without switching anything. Degradation only changes routing for NEW calls.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Literal

log = logging.getLogger(__name__)


class LegState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass
class LegThresholds:
    trip_p95_ms: float
    recover_p95_ms: float
    alert_p95_ms: float | None = None
    trip_error_rate: float | None = None
    recover_error_rate: float | None = None
    trip_minutes: int = 3
    recover_minutes: int = 10
    window_s: float = 300.0
    min_samples: int = 50


@dataclass
class Sample:
    t: float
    latency_ms: float | None
    error: bool
    source: str


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, int(round(0.95 * len(ordered) + 0.5)) - 1)
    return ordered[min(rank, len(ordered) - 1)]


class LegMonitor:
    def __init__(self, name: str, thresholds: LegThresholds,
                 on_alert: Callable[[str, float], None] | None = None,
                 on_state_change: Callable[[str, LegState], None] | None = None):
        self.name = name
        self.t = thresholds
        self.on_alert = on_alert
        self.on_state_change = on_state_change
        self.state = LegState.HEALTHY
        self.alerting = False
        self._samples: deque[Sample] = deque()
        self._trip_streak = 0
        self._recover_streak = 0

    def record(self, now: float, latency_ms: float | None = None, error: bool = False, source: str = "live") -> None:
        self._samples.append(Sample(now, latency_ms, error, source))

    def stats(self, now: float) -> tuple[float | None, float | None, int]:
        while self._samples and now - self._samples[0].t > self.t.window_s:
            self._samples.popleft()
        n = len(self._samples)
        if n == 0:
            return None, None, 0
        latencies = [s.latency_ms for s in self._samples if s.latency_ms is not None]
        errors = sum(1 for s in self._samples if s.error)
        return p95(latencies), errors / n, n

    def tick(self, now: float) -> LegState:
        """Call once per minute."""
        p, err, n = self.stats(now)
        enough = n >= self.t.min_samples
        if enough and self.t.alert_p95_ms is not None and p is not None:
            if p > self.t.alert_p95_ms and not self.alerting:
                self.alerting = True
                log.warning("ALERT %s p95 %.0f ms > %.0f ms", self.name, p, self.t.alert_p95_ms)
                if self.on_alert:
                    self.on_alert(self.name, p)
            elif p <= self.t.alert_p95_ms:
                self.alerting = False

        if not enough:
            return self.state  # no evidence: hold streaks
        slow = p is not None and p > self.t.trip_p95_ms
        failing = self.t.trip_error_rate is not None and err is not None and err > self.t.trip_error_rate
        if self.state == LegState.HEALTHY:
            self._trip_streak = self._trip_streak + 1 if (slow or failing) else 0
            if self._trip_streak >= self.t.trip_minutes:
                self._set(LegState.DEGRADED)
        else:
            fast = p is None or p < self.t.recover_p95_ms
            clean = self.t.recover_error_rate is None or (err is not None and err < self.t.recover_error_rate)
            self._recover_streak = self._recover_streak + 1 if (fast and clean) else 0
            if self._recover_streak >= self.t.recover_minutes:
                self._set(LegState.HEALTHY)
        return self.state

    def needs_probe_samples(self, now: float) -> bool:
        _, _, n = self.stats(now)
        return self.state == LegState.DEGRADED or n < self.t.min_samples

    def _set(self, state: LegState) -> None:
        self.state = state
        self._trip_streak = 0
        self._recover_streak = 0
        log.warning("leg %s -> %s", self.name, state)
        if self.on_state_change:
            self.on_state_change(self.name, state)


Route = Literal["primary", "fallback"]


@dataclass
class RouteDecision:
    stt: Route
    llm: Route
    callback_only: bool


class RoutingPolicy:
    def __init__(self, llm_leg: LegMonitor, stt_leg: LegMonitor, nova3_floor_passed: bool,
                 llm_fallback_available: bool = True):
        self.llm_leg = llm_leg
        self.stt_leg = stt_leg
        self.nova3_floor_passed = nova3_floor_passed
        self.llm_fallback_available = llm_fallback_available

    def for_new_call(self) -> RouteDecision:
        stt: Route = "fallback" if self.stt_leg.state == LegState.DEGRADED else "primary"
        # Without a fallback LLM a slow primary is still better than none: alert only, never reroute.
        llm_degraded = self.llm_leg.state == LegState.DEGRADED and self.llm_fallback_available
        llm: Route = "fallback" if llm_degraded else "primary"
        return RouteDecision(stt=stt, llm=llm, callback_only=self.callback_only_for(stt))

    def callback_only_for(self, stt: Route) -> bool:
        return stt == "fallback" and not self.nova3_floor_passed

    @property
    def outbound_paused(self) -> bool:
        return self.for_new_call().callback_only
