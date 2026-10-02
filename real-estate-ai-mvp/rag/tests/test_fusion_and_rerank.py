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
