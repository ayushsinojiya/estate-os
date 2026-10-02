"""The retrieval core shared by the live-call endpoint and the CRM search endpoint."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from rag_service.config import Settings
from rag_service.providers.llm import JsonModel
from rag_service.retrieve import rerank as rerank_mod
from rag_service.retrieve.rewrite import rewrite
from rag_service.retrieve.search import Candidate, Scope, Searcher, rrf


@dataclass
class Retrieval:
    items: list[Candidate]
    queries: list[str]
    rerank: str
    timings_ms: dict[str, float] = field(default_factory=dict)


class Retriever:
    def __init__(self, settings: Settings, searcher: Searcher, reranker: rerank_mod.Reranker | None,
                 json_model: JsonModel | None):
        self.settings = settings
        self.searcher = searcher
        self.reranker = reranker
        self.json_model = json_model

    async def run(self, scope: Scope, query: str, k: int, *, rewrite_query: bool) -> Retrieval:
        s = self.settings
        timings: dict[str, float] = {}
        started = time.perf_counter()
        queries = await rewrite(self.json_model, query) if rewrite_query else [query]
        if rewrite_query:
            timings["rewrite"] = (time.perf_counter() - started) * 1000
        t = time.perf_counter()
        vectors = await self.searcher.embed_queries(queries)
        timings["embed"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        lists = await self.searcher.candidates(scope, queries, vectors)
        timings["search"] = (time.perf_counter() - t) * 1000
        names = [f"{kind}{n}" for n in range(len(queries)) for kind in ("vector", "keyword", "names")]
        fused = rrf(lists, s.rrf_k, names)
        top = fused[:s.rerank_candidates]
        t = time.perf_counter()
        documents = [f"{c.row['context_header']}\n{c.row['content']}"[:1500] for c in top]
        scores, status = await rerank_mod.apply(self.reranker, queries[0], documents, s.rerank_budget_ms) \
            if top else (None, "skipped:empty")
        timings["rerank"] = (time.perf_counter() - t) * 1000
        if scores is not None:
            for candidate, score in zip(top, scores):
                candidate.rerank_score = score
            top.sort(key=lambda c: (-(c.rerank_score or 0.0), -c.score))
        timings["total"] = (time.perf_counter() - started) * 1000
        return Retrieval(top[:k], queries, status, {key: round(v, 1) for key, v in timings.items()})
