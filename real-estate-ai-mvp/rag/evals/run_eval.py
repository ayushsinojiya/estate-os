"""Retrieval eval: recall@4 and MRR over a synthetic brochure, price sheet and FAQ.

    .venv/bin/python -m evals.run_eval            # Testcontainers pgvector, providers from env
    PROVIDER_MODE=fake .venv/bin/python -m evals.run_eval

Two paths are measured, because the service has two:

- voice:  /v1/voice/retrieve with the English keyword query the voice LLM is instructed to write;
- crm:    /v1/knowledge/search with the caller's own words (en/hi/mr/gu), rewritten to English by
          the rewrite model when one is configured.

A question counts as found at rank r when the r-th result contains its expected text. This is not
a CI gate; the numbers go into rag/README.md.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from rag_service.api import create_app  # noqa: E402
from rag_service.config import Settings  # noqa: E402
from rag_service.migrate import migrate  # noqa: E402
from rag_service.services import build_services  # noqa: E402
from rag_service.worker import run_once  # noqa: E402

TOKEN = "eval-token-0123456789abcdef0123456789"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
PROJECT = {"projectId": "11", "projectName": "Sahyadri Grove", "locality": "Baner, Pune"}


def price_sheet() -> bytes:
    import openpyxl

    book = openpyxl.Workbook()
    charges = book.active
    charges.title = "Charges"
    charges.append(["Charge", "Amount", "Notes"])
    for row in [
        ("Floor rise", "₹40 per sq ft per floor", "Applies from the 6th floor upwards"),
        ("PLC — garden facing", "₹150 per sq ft", "Preferential location charge for central-lawn views"),
        ("PLC — corner flat", "₹100 per sq ft", "Preferential location charge"),
        ("Covered car parking", "Included", "One with 2 BHK, two with 3 BHK"),
        ("Club membership", "₹2,00,000", "One-time, payable at possession"),
        ("Maintenance deposit", "24 months at ₹4.50 per sq ft per month", "Collected at possession"),
        ("Legal and documentation", "₹25,000", "One-time"),
        ("GST", "5% of agreement value", "Under-construction homes; not applicable on stamp duty"),
        ("Stamp duty and registration", "As per government rates", "Paid directly by the buyer"),
    ]:
        charges.append(list(row))
    plan = book.create_sheet("Payment plan")
    plan.append(["Stage", "Due", "Percent of agreement value"])
    for row in [("On booking", "At booking", "10%"), ("Agreement", "Within 30 days", "10%"),
                ("Plinth", "Plinth completion", "15%"), ("Slab 1–5", "Every slab", "5% each"),
                ("Slab 6–22", "Every third slab", "5% each"), ("Brickwork and plaster", "On completion", "10%"),
                ("Possession", "On offer of possession", "5%")]:
        plan.append(list(row))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


async def ingest(client, services) -> None:
    files = [
        ("sahyadri-grove-brochure.md", (HERE / "corpus" / "sahyadri-grove-brochure.md").read_bytes(), "BROCHURE"),
        ("sahyadri-grove-faq.md", (HERE / "corpus" / "sahyadri-grove-faq.md").read_bytes(), "FAQ"),
        ("sahyadri-grove-price-sheet.xlsx", price_sheet(), "PRICE_SHEET"),
    ]
    for crm_id, (name, data, doc_type) in enumerate(files, start=901):
        response = await client.post("/v1/workspaces/1/sources", headers=HEADERS, files=[("files", (name, data))],
                                     data={**PROJECT, "crmDocumentId": str(crm_id), "docType": doc_type})
        assert response.status_code == 202, response.text
    while await run_once(services, "eval"):
        pass
    listed = (await client.get("/v1/workspaces/1/sources", headers=HEADERS)).json()
    assert all(i["status"] == "PUBLISHED" for i in listed["items"]), listed


def rank_of(results: list[dict], expect: str, field: str) -> int | None:
    for rank, row in enumerate(results, start=1):
        if expect.lower() in row[field].lower():
            return rank
    return None


async def evaluate(client) -> dict:
    golden = json.loads((HERE / "golden.json").read_text())
    rows = []
    for item in golden:
        voice = (await client.post("/v1/voice/retrieve", headers=HEADERS, json={
            "workspaceId": 1, "projectId": 11, "query": item["voice_query"], "k": 4})).json()
        crm = (await client.post("/v1/knowledge/search", headers=HEADERS, json={
            "workspaceId": "1", "projectId": "11", "query": item["question"], "language": item["lang"],
            "publishedDocumentIds": ["901", "902", "903"], "k": 4})).json()
        rows.append({**item, "voice_rank": rank_of(voice["results"], item["expect"], "content"),
                     "crm_rank": rank_of(crm["results"], item["expect"], "text"),
                     "voice_ms": voice["timingsMs"]["total"], "rewritten": crm.get("queries")})
    return summarise(rows)


def summarise(rows: list[dict]) -> dict:
    def metrics(subset: list[dict], key: str) -> dict:
        found = [r[key] for r in subset]
        return {"n": len(subset), "recall@4": round(sum(1 for f in found if f) / len(subset), 3),
                "mrr": round(statistics.mean(1 / f if f else 0.0 for f in found), 3)}

    by_lang = defaultdict(list)
    for row in rows:
        by_lang[row["lang"]].append(row)
    return {
        "voice": metrics(rows, "voice_rank"), "crm": metrics(rows, "crm_rank"),
        "by_language": {lang: {"voice": metrics(sub, "voice_rank"), "crm": metrics(sub, "crm_rank")}
                        for lang, sub in sorted(by_lang.items())},
        "voice_latency_ms_p50": statistics.median(r["voice_ms"] for r in rows),
        "misses": [{k: r[k] for k in ("lang", "question", "voice_query", "expect", "voice_rank", "crm_rank")}
                   for r in rows if not (r["voice_rank"] and r["crm_rank"])],
    }


async def main() -> None:
    url = os.environ.get("RAG_DATABASE_URL")
    container = None
    if not url:
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("pgvector/pgvector:pg17", driver=None)
        container.start()
        url = container.get_connection_url()
    try:
        mode = os.environ.get("PROVIDER_MODE") or ("live" if os.environ.get("OPENAI_API_KEY") else "fake")
        settings = Settings(rag_database_url=url, provider_mode=mode, rag_service_token=TOKEN,
                            rag_storage_path=HERE / "results" / "storage",
                            reranker=os.environ.get("RERANKER", "none" if mode == "fake" else "bge"))
        migrate(settings)
        services = build_services(settings)
        await services.db.open()
        app = create_app(settings, services=services)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://rag") as client:
                await ingest(client, services)
                result = await evaluate(client)
                reranker = app.state.retriever.reranker
        result["config"] = {"provider_mode": mode, "embedding_model": settings.effective_embedding_model,
                            "reranker": reranker.name if reranker else "none",
                            "rewrite": settings.rewrite_model if services.json_model else "none (no model offline)"}
        out = HERE / "results"
        out.mkdir(exist_ok=True)
        (out / "latest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(json.dumps({k: v for k, v in result.items() if k != "misses"}, indent=2, ensure_ascii=False))
        print(f"{len(result['misses'])} questions missed on at least one path (see evals/results/latest.json)")
    finally:
        if container is not None:
            container.stop()


if __name__ == "__main__":
    asyncio.run(main())
