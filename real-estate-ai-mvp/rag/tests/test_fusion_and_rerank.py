"""Reciprocal Rank Fusion, and the rerank step's latency budget."""

import asyncio

from rag_service.retrieve import rerank
from rag_service.retrieve.search import rrf, tsquery


def _rows(*ids):
    return [{"id": i} for i in ids]


def test_rrf_rewards_agreement_between_lists():
    fused = rrf([_rows(1, 2, 3), _rows(3, 1, 4)], k=60)
    assert [c.id for c in fused[:2]] == [1, 3]
    assert abs(fused[0].score - (1 / 61 + 1 / 62)) < 1e-12
    assert fused[0].ranks == {"0": 1, "1": 2}
    # Appearing in only one list, even first, ranks below an item both lists found.
    assert fused[-1].id in (2, 4)


def test_rrf_handles_empty_lists():
    assert rrf([[], []]) == []
    assert [c.id for c in rrf([_rows(7), []])] == [7]


def test_tsquery_is_an_or_query_of_meaningful_terms():
    assert tsquery("What is the floor-rise charge?") == "floor:* | rise:* | charge:*"
    assert tsquery("RERA P52100012345") == "rera:* | p52100012345"
    assert tsquery("the of is") is None


def test_rerank_is_skipped_when_predicted_over_budget():
    slow = rerank.OverlapReranker(delay_ms=400)
    scores, status = asyncio.run(rerank.apply(slow, "q", ["a"] * 20, budget_ms=150))
    assert scores is None and status == "skipped:budget"


def test_rerank_that_overruns_is_cut_off_at_the_budget():
    liar = rerank.OverlapReranker(delay_ms=300)
    liar.ms_per_pair = 0.1  # predicts it will be fast
    scores, status = asyncio.run(rerank.apply(liar, "q", ["a"] * 5, budget_ms=50))
    assert scores is None and status == "skipped:timeout"


def test_rerank_within_budget_is_applied():
    fast = rerank.OverlapReranker()
    scores, status = asyncio.run(rerank.apply(fast, "club house", ["club house gym", "parking"], budget_ms=150))
    assert status == "applied" and scores[0] > scores[1]


def test_no_reranker_is_reported_as_disabled():
    assert asyncio.run(rerank.apply(None, "q", ["a"], 150)) == (None, "disabled")


def test_voice_snippets_keep_the_relevant_sentences():
    from rag_service.retrieve.snippet import focus

    content = " ".join(f"Filler sentence number {i} about nothing in particular." for i in range(30))
    content += " Vitrified tiles of 800 x 800 mm in the living and dining areas. " + content
    short = focus(content, "living room flooring tiles", 200)
    assert "800 x 800 mm" in short and len(short) <= 200
    table = "| Charge | Amount |\n|---|---|\n" + "\n".join(f"| Item {i} | ₹{i} |" for i in range(80)) + "\n| Floor rise | ₹40 |"
    focused = focus(table, "floor rise charge", 120, "TABLE")
    assert focused.startswith("| Charge | Amount |\n|---|---|") and "Floor rise" in focused


class _SlowSearcher:
    """Embedding slower than the budget (or failing); the searches themselves are instant."""

    def __init__(self, delay_s: float = 0.0, fail: bool = False):
        self.delay_s, self.fail, self.embedded, self.seen_vectors = delay_s, fail, 0, "unset"

    async def embed_queries(self, queries):
        await asyncio.sleep(self.delay_s)
        if self.fail:
            raise RuntimeError("provider down")
        self.embedded += 1
        return [[0.0] for _ in queries]

    async def candidates(self, scope, queries, vectors):
        self.seen_vectors = vectors
        return [[], [{"id": i, "context_header": "", "content": ""} for i in (5, 6)], []]


def _retriever(searcher):
    from rag_service.config import Settings
    from rag_service.retrieve.retriever import Retriever
    from rag_service.retrieve.search import Scope
    return Retriever(Settings(reranker="none"), searcher, None, None), Scope(1)


def test_voice_answers_from_keyword_search_when_embedding_is_over_budget():
    async def go():
        searcher = _SlowSearcher(delay_s=0.2)
        retriever, scope = _retriever(searcher)
        result = await retriever.run(scope, "payment plan", 4, rewrite_query=False, embed_budget_ms=20)
        assert result.vector == "skipped:budget" and searcher.seen_vectors is None
        assert [c.id for c in result.items] == [5, 6]
        assert result.timings_ms["total"] < 150
        await asyncio.sleep(0.3)
        assert searcher.embedded == 1  # the late embedding still completed (and was cached)
    asyncio.run(go())


def test_embedding_failure_falls_back_to_keyword_search():
    retriever, scope = _retriever(_SlowSearcher(fail=True))
    result = asyncio.run(retriever.run(scope, "q", 4, rewrite_query=False, embed_budget_ms=300))
    assert result.vector == "skipped:error" and [c.id for c in result.items] == [5, 6]


def test_no_budget_waits_for_the_embedding():
    searcher = _SlowSearcher(delay_s=0.05)
    retriever, scope = _retriever(searcher)
    result = asyncio.run(retriever.run(scope, "q", 4, rewrite_query=False))
    assert result.vector == "ok" and searcher.seen_vectors == [[0.0]]


def test_rate_limited_calls_wait_as_long_as_the_provider_asks(monkeypatch):
    import httpx
    from rag_service.providers import http as provider_http
    calls, waits = [], []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after-ms": "7300"}, json={"error": "rate limit"})
        return httpx.Response(200, json={"ok": True})

    async def fake_sleep(seconds):
        waits.append(seconds)
    monkeypatch.setattr(provider_http.asyncio, "sleep", fake_sleep)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await provider_http.post_json(client, "https://x.test", headers={}, payload={})
    assert asyncio.run(go()) == {"ok": True}
    assert waits == [7.3]
