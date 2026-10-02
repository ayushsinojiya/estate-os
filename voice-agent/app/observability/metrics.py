"""In-process counters and latency summaries, exposed as JSON at /metrics."""

from __future__ import annotations

import threading
from collections import defaultdict, deque


class Metrics:
    def __init__(self, window: int = 500):
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._timings: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))

    def inc(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] += by

    def observe(self, name: str, value_ms: float) -> None:
        with self._lock:
            self._timings[name].append(value_ms)

    def snapshot(self) -> dict:
        with self._lock:
            timings = {}
            for name, values in self._timings.items():
                ordered = sorted(values)
                if ordered:
                    timings[name] = {"n": len(ordered), "p50": ordered[len(ordered) // 2],
                                     "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]}
            return {"counters": dict(self._counters), "timings_ms": timings}
