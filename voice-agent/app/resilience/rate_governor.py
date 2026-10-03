"""Client-side Sarvam rate governor (spec section 7).

One account-wide sliding-window limiter set below Sarvam's written limit. Live turns have
priority; probes and deferred work (post-call summaries, lead scoring) use lower ceilings so
live turns keep headroom. A live turn that cannot get a slot in time goes to the fallback LLM.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from enum import IntEnum
from typing import Callable


class Priority(IntEnum):
    LIVE = 0
    PROBE = 1
    DEFERRED = 2


class RateGovernor:
    def __init__(self, limit_per_min: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic,
                 probe_ceiling: float = 0.9, deferred_ceiling: float = 0.7):
        self.limit = limit_per_min
        self.window_s = window_s
        self.clock = clock
        self._ceilings = {Priority.LIVE: 1.0, Priority.PROBE: probe_ceiling, Priority.DEFERRED: deferred_ceiling}
        self._stamps: deque[float] = deque()
        self.granted = {p: 0 for p in Priority}
        self.rejected = {p: 0 for p in Priority}

    def _prune(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] >= self.window_s:
            self._stamps.popleft()

    def used(self, now: float | None = None) -> int:
        self._prune(self.clock() if now is None else now)
        return len(self._stamps)

    def headroom(self, now: float | None = None) -> int:
        return max(0, self.limit - self.used(now))

    def utilisation(self) -> float:
        return self.used() / self.limit if self.limit else 1.0

    def try_acquire(self, priority: Priority = Priority.LIVE, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        self._prune(now)
        ceiling = math.floor(self.limit * self._ceilings[priority])
        if len(self._stamps) < ceiling:
            self._stamps.append(now)
            self.granted[priority] += 1
            return True
        return False

    async def acquire(self, priority: Priority = Priority.LIVE, max_wait_s: float = 0.15) -> bool:
        deadline = self.clock() + max_wait_s
        while True:
            if self.try_acquire(priority):
                return True
            now = self.clock()
            if now >= deadline:
                self.rejected[priority] += 1
                return False
            until_free = self.window_s - (now - self._stamps[0]) if self._stamps else 0.01
            await asyncio.sleep(max(0.001, min(deadline - now, until_free, 0.01)))
