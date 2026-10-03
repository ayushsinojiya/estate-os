"""Primary/fallback LLM routing with the rate governor and hard-failure rules (spec sections 7, 30).

Hard failure on the primary (connection error, 5xx, 429, governor rejection, no first token within
the timeout) moves this call to the fallback for the rest of the call. Every primary outcome is
recorded on the LLM leg monitor; failures count as a timeout-length sample so they raise p95.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from app.llm.base import LLMError, LLMEvent, LLMProvider, Message, ToolSpec
from app.resilience.degradation import LegMonitor
from app.resilience.rate_governor import Priority, RateGovernor

log = logging.getLogger(__name__)


class AllProvidersFailed(RuntimeError):
    pass


@dataclass
class LLMRoute:
    use_fallback: bool = False
    reason: str | None = None
    provider_used: str | None = None
    last_ttft_ms: float | None = None


async def _close(agen) -> None:
    try:
        await agen.aclose()
    except Exception:  # noqa: BLE001 - closing a failed stream must never raise
        pass


class LLMRouter:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None, *, governor: RateGovernor | None = None,
                 leg: LegMonitor | None = None, first_token_timeout_s: float = 2.0,
                 fallback_first_token_timeout_s: float = 5.0, live_max_wait_s: float = 0.15,
                 clock: Callable[[], float] = time.monotonic):
        self.primary = primary
        self.fallback = fallback
        self.governor = governor
        self.leg = leg
        self.first_token_timeout_s = first_token_timeout_s
        self.fallback_first_token_timeout_s = fallback_first_token_timeout_s
        self.live_max_wait_s = live_max_wait_s
        self.clock = clock

    async def stream(self, route: LLMRoute, build_messages: Callable[[str], list[Message]], tools: list[ToolSpec],
                     **kwargs) -> AsyncIterator[LLMEvent]:
        if self.fallback is None:
            async for event in self._primary_only(route, build_messages, tools, kwargs):
                yield event
            return
        if not route.use_fallback:
            async for event in self._primary(route, build_messages, tools, kwargs):
                yield event
            if not route.use_fallback:
                return
        async for event in self._fallback(route, build_messages, tools, kwargs):
            yield event

    def _record_failure(self) -> None:
        if self.leg:
            self.leg.record(self.clock(), latency_ms=self.first_token_timeout_s * 1000, error=True)

    def _fail(self, route: LLMRoute, reason: str) -> None:
        route.use_fallback = True
        route.reason = reason
        log.warning("LLM primary hard failure (%s); call moves to fallback", reason)
        self._record_failure()

    async def _primary_only(self, route, build_messages, tools, kwargs) -> AsyncIterator[LLMEvent]:
        """No fallback configured: wait longer for the primary; on failure the session gives the safe response
        and the next turn tries the primary again."""
        wait_s = self.fallback_first_token_timeout_s
        if self.governor and not await self.governor.acquire(Priority.LIVE, wait_s):
            self._record_failure()
            route.reason = "governor_rejected"
            raise AllProvidersFailed("no rate-governor slot and no fallback LLM")
        start = self.clock()
        agen = self.primary.stream(build_messages(self.primary.name), tools, **kwargs)
        try:
            first = await asyncio.wait_for(agen.__anext__(), wait_s)
        except StopAsyncIteration:
            route.provider_used = self.primary.name
            return
        except (asyncio.TimeoutError, LLMError) as exc:
            await _close(agen)
            self._record_failure()
            route.reason = f"primary_failed_no_fallback:{type(exc).__name__}"
            raise AllProvidersFailed(f"primary failed and no fallback LLM: {exc!r}") from exc
        ttft_ms = (self.clock() - start) * 1000
        route.provider_used, route.last_ttft_ms = self.primary.name, ttft_ms
        if self.leg:
            self.leg.record(self.clock(), latency_ms=ttft_ms)
        yield first
        try:
            async for event in agen:
                yield event
        except LLMError as exc:
            self._record_failure()
            raise AllProvidersFailed(f"primary failed mid-stream and no fallback LLM: {exc!r}") from exc

    async def _primary(self, route, build_messages, tools, kwargs) -> AsyncIterator[LLMEvent]:
        if self.governor and not await self.governor.acquire(Priority.LIVE, self.live_max_wait_s):
            self._fail(route, "governor_rejected")
            return
        start = self.clock()
        agen = self.primary.stream(build_messages(self.primary.name), tools, **kwargs)
        try:
            first = await asyncio.wait_for(agen.__anext__(), self.first_token_timeout_s)
        except StopAsyncIteration:
            route.provider_used = self.primary.name
            return
        except asyncio.TimeoutError:
            await _close(agen)
            self._fail(route, "first_token_timeout")
            return
        except LLMError as exc:
            await _close(agen)
            self._fail(route, f"primary_{exc.kind}")
            return
        ttft_ms = (self.clock() - start) * 1000
        route.provider_used, route.last_ttft_ms = self.primary.name, ttft_ms
        if self.leg:
            self.leg.record(self.clock(), latency_ms=ttft_ms)
        yield first
        try:
            async for event in agen:
                yield event
        except LLMError as exc:
            self._fail(route, f"primary_mid_stream_{exc.kind}")
            raise

    async def _fallback(self, route, build_messages, tools, kwargs) -> AsyncIterator[LLMEvent]:
        start = self.clock()
        agen = self.fallback.stream(build_messages(self.fallback.name), tools, **kwargs)
        try:
            first = await asyncio.wait_for(agen.__anext__(), self.fallback_first_token_timeout_s)
        except StopAsyncIteration:
            route.provider_used = self.fallback.name
            return
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001 - any fallback failure ends in the safe response
            await _close(agen)
            raise AllProvidersFailed(f"fallback failed: {exc!r}") from exc
        route.provider_used, route.last_ttft_ms = self.fallback.name, (self.clock() - start) * 1000
        yield first
        try:
            async for event in agen:
                yield event
        except LLMError as exc:
            raise AllProvidersFailed(f"fallback failed mid-stream: {exc!r}") from exc
