"""/v1/voice/retrieve latency, server side, with providers mocked at realistic speeds.

The embedding call is simulated at 120 ms (a typical OpenAI round trip from India) and the
reranker at 60 ms for 20 pairs. The target is p95 < 450 ms including the embedding call.
"""

import asyncio
import statistics
import time

import pytest

from rag_service.api import create_app
from rag_service.providers.embeddings import HashingEmbedder
from rag_service.retrieve.rerank import OverlapReranker
from tests.conftest import _client, drain, upload, VOICE

EMBED_MS, RERANK_MS = 120, 60


class SlowEmbedder(HashingEmbedder):
    async def embed(self, texts):
        await asyncio.sleep(EMBED_MS / 1000)
        return await super().embed(texts)


AREAS = ["Baner", "Wakad", "Kharadi", "Hinjawadi", "Aundh", "Hadapsar", "Kothrud", "Viman Nagar"]
TOPICS = ["clubhouse and gym", "payment plan stages", "floor rise charges", "possession timeline",
          "car parking", "RERA registration", "school and hospital nearby", "maintenance deposit"]


def _document(n: int) -> str:
    parts = [f"# Project {n} in {AREAS[n % len(AREAS)]}"]
    for t, topic in enumerate(TOPICS):
        parts.append(f"## {topic.title()}\n\n" + " ".join(
            f"Project {n} offers details about {topic} for tower {k}, sentence {k} of the section." for k in range(12)))
    return "\n\n".join(parts)


async def test_voice_retrieve_p95_under_450ms(settings, services):
    services.embedder = SlowEmbedder(settings.embedding_dim)
    app = create_app(settings, services=services, reranker=OverlapReranker(delay_ms=RERANK_MS))
    async with _client(app) as client:
        for n in range(24):
            await upload(client, 1, f"project-{n}.md", _document(n).encode(), projectId=100 + n % 4)
        await drain(services, limit=100)
        async with services.db.conn() as conn:
            chunks = (await (await conn.execute("SELECT count(*) AS n FROM kb_chunks WHERE status='PUBLISHED'")).fetchone())["n"]
        assert chunks >= 200

        timings, server = [], []
        for i in range(60):
            query = f"{TOPICS[i % len(TOPICS)]} in {AREAS[i % len(AREAS)]} option {i}"
            started = time.perf_counter()
            response = await client.post("/v1/voice/retrieve", headers=VOICE,
                                         json={"workspaceId": 1, "projectId": 100 + i % 4, "query": query})
            timings.append((time.perf_counter() - started) * 1000)
            body = response.json()
            assert response.status_code == 200 and body["results"]
            server.append(body["timingsMs"]["total"])
    ordered = sorted(timings)
    p50, p95 = statistics.median(ordered), ordered[int(len(ordered) * 0.95) - 1]
    print(f"\nvoice/retrieve over {chunks} chunks: p50 {p50:.0f} ms, p95 {p95:.0f} ms "
          f"(server-reported p95 {sorted(server)[int(len(server) * 0.95) - 1]:.0f} ms; "
          f"embed {EMBED_MS} ms + rerank {RERANK_MS} ms simulated)")
    assert p95 < 450
