"""Rerankers, with a latency budget.

The live-call path has about 450 ms in total. Reranking is worth it only if it fits: each reranker
predicts its own latency for the candidates in hand (from a running average of what it actually
took), and when the prediction exceeds RERANK_BUDGET_MS the step is skipped and the fused order is
used. A call that overruns anyway is cut off at the budget.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class Reranker(Protocol):
    name: str

    def predict_ms(self, pairs: int) -> float: ...
    async def score(self, query: str, documents: list[str]) -> list[float]: ...


class _Timed:
    def __init__(self, initial_ms_per_pair: float):
        self.ms_per_pair = initial_ms_per_pair
        self.overhead_ms = 0.0

    def predict_ms(self, pairs: int) -> float:
        return self.overhead_ms + self.ms_per_pair * pairs

    def observe(self, pairs: int, elapsed_ms: float) -> None:
        per_pair = elapsed_ms / max(1, pairs)
        self.ms_per_pair = 0.7 * self.ms_per_pair + 0.3 * per_pair


class BgeReranker(_Timed):
    """BAAI/bge-reranker-v2-m3 (multilingual cross-encoder) on CPU, loaded once at startup."""

    def __init__(self, model_name: str, max_length: int = 384):
        super().__init__(initial_ms_per_pair=8.0)
        self.name = f"bge:{model_name}"
        self.model_name = model_name
        self.max_length = max_length
        self._model = None
        self._lock = asyncio.Lock()

    def load(self) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self.model_name, max_length=self.max_length, device="cpu")
        started = time.perf_counter()
        self._model.predict([("warm up", "warm up the cross encoder")] * 4)
        self.observe(4, (time.perf_counter() - started) * 1000)

    @property
    def ready(self) -> bool:
        return self._model is not None

    async def score(self, query: str, documents: list[str]) -> list[float]:
        if self._model is None:
            raise RuntimeError("reranker model not loaded")
        async with self._lock:  # one inference at a time: CPU threads are the bottleneck
            started = time.perf_counter()
            scores = await asyncio.to_thread(self._model.predict, [(query, d) for d in documents])
            self.observe(len(documents), (time.perf_counter() - started) * 1000)
        return [float(s) for s in scores]


class CohereReranker(_Timed):
    def __init__(self, api_key: str, model: str, client: httpx.AsyncClient):
        super().__init__(initial_ms_per_pair=4.0)
        self.overhead_ms = 80.0
        self.name = f"cohere:{model}"
        self.model = model
        self._client = client
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def score(self, query: str, documents: list[str]) -> list[float]:
        started = time.perf_counter()
        response = await self._client.post("https://api.cohere.com/v2/rerank", headers=self._headers,
                                           json={"model": self.model, "query": query, "documents": documents},
                                           timeout=2.0)
        response.raise_for_status()
        scores = [0.0] * len(documents)
        for item in response.json()["results"]:
            scores[item["index"]] = float(item["relevance_score"])
        self.observe(len(documents), (time.perf_counter() - started) * 1000)
        return scores


class OverlapReranker(_Timed):
    """Offline stand-in: scores by shared words. Used in fake mode and tests."""

    def __init__(self, delay_ms: float = 0.0):
        super().__init__(initial_ms_per_pair=delay_ms / 20 if delay_ms else 0.05)
        self.name = "overlap"
        self.delay_ms = delay_ms

    async def score(self, query: str, documents: list[str]) -> list[float]:
        started = time.perf_counter()
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        words = set(query.lower().split())
        out = [len(words & set(d.lower().split())) / (1 + len(words)) for d in documents]
        self.observe(len(documents), (time.perf_counter() - started) * 1000)
        return out


async def apply(reranker: Reranker | None, query: str, documents: list[str],
                budget_ms: float) -> tuple[list[float] | None, str]:
    """Scores, or None with the reason reranking did not happen."""
    if reranker is None:
        return None, "disabled"
    if getattr(reranker, "ready", True) is False:
        return None, "skipped:not_loaded"
    predicted = reranker.predict_ms(len(documents))
    if predicted > budget_ms:
        log.info("rerank skipped: predicted %.0f ms for %d pairs exceeds the %.0f ms budget",
                 predicted, len(documents), budget_ms)
        return None, "skipped:budget"
    try:
        return await asyncio.wait_for(reranker.score(query, documents), budget_ms / 1000), "applied"
    except asyncio.TimeoutError:
        log.info("rerank skipped: exceeded the %.0f ms budget", budget_ms)
        return None, "skipped:timeout"
    except Exception as exc:  # noqa: BLE001 - reranking is an optimisation, never a failure
        log.warning("rerank failed: %r", exc)
        return None, "skipped:error"
