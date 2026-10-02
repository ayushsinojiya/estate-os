"""Synthetic LLM probes (spec section 30).

While traffic is routed away from Sarvam, or real traffic is too low to fill the window, probes
send the real system prompt with a fixed short turn so the LLM leg keeps getting samples and
recovery can be detected.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from app.llm.base import LLMError, LLMProvider, Message
from app.resilience.degradation import LegMonitor, LegState
from app.resilience.rate_governor import Priority, RateGovernor

log = logging.getLogger(__name__)

class LLMProbe:
    def __init__(self, provider: LLMProvider, leg: LegMonitor, governor: RateGovernor | None = None,
                 interval_s: float = 30.0, timeout_s: float = 2.0, clock: Callable[[], float] = time.monotonic,
                 active_calls: Callable[[], int] = lambda: 1,
                 messages: Callable[[], list[Message]] = lambda: [Message("user", "hello")]):
        self.provider = provider
        self.messages = messages
        self.leg = leg
        self.governor = governor
        self.interval_s = interval_s
        self.timeout_s = timeout_s
        self.clock = clock
        self.active_calls = active_calls

    def should_probe(self) -> bool:
        """Probe while traffic is routed away (to detect recovery), or during calls when real samples are too few.
        With no calls and a healthy leg there is nothing to measure, so no requests are spent."""
        if self.leg.state == LegState.DEGRADED:
            return True
        return self.active_calls() > 0 and self.leg.needs_probe_samples(self.clock())

    async def run_once(self) -> bool:
        if not self.should_probe():
            return False
        if self.governor is not None and not self.governor.try_acquire(Priority.PROBE):
            return False
        # The domain supplies its real system prompt, so the probe measures what calls pay.
        messages = self.messages()
        start = self.clock()
        agen = self.provider.stream(messages, [], max_tokens=8, temperature=0.0)
        try:
            await asyncio.wait_for(agen.__anext__(), self.timeout_s)
            self.leg.record(self.clock(), latency_ms=(self.clock() - start) * 1000, source="probe")
        except (asyncio.TimeoutError, LLMError, StopAsyncIteration) as exc:
            log.info("LLM probe failed: %r", exc)
            self.leg.record(self.clock(), latency_ms=self.timeout_s * 1000, error=True, source="probe")
        finally:
            try:
                await agen.aclose()
            except Exception:  # noqa: BLE001
                pass
        return True

    async def loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:  # noqa: BLE001 - probes must never take the service down
                log.exception("probe loop error")
            await asyncio.sleep(self.interval_s)
