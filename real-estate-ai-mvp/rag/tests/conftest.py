"""Fixtures: a real pgvector Postgres (Testcontainers), the service in fake provider mode."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import httpx
import pytest
from testcontainers.postgres import PostgresContainer

from rag_service.api import create_app
from rag_service.config import Settings
from rag_service.migrate import migrate
from rag_service.retrieve.rerank import OverlapReranker
from rag_service.services import build_services
from rag_service.worker import run_once

CRM_TOKEN = "crm-token-for-tests-0123456789abcdef"
VOICE_TOKEN = "voice-token-for-tests-0123456789abcd"
CRM = {"Authorization": f"Bearer {CRM_TOKEN}"}
VOICE = {"Authorization": f"Bearer {VOICE_TOKEN}"}


@pytest.fixture(scope="session")
def database_url():
    external = os.environ.get("TEST_RAG_DATABASE_URL")
    if external:
        yield external
        return
    with PostgresContainer("pgvector/pgvector:pg17", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated(database_url):
    migrate(Settings(rag_database_url=database_url, provider_mode="fake", embedding_dim=256))
    return database_url


@pytest.fixture
def settings(migrated, tmp_path):
    return Settings(rag_database_url=migrated, provider_mode="fake", embedding_dim=256,
                    rag_storage_path=tmp_path / "storage", rag_service_token=CRM_TOKEN,
                    rag_voice_token=VOICE_TOKEN, rag_voice_workspace_id=1, db_pool_min=1, db_pool_max=8,
                    job_backoff_s=0.01, chunk_min_tokens=60, chunk_target_tokens=120, chunk_max_tokens=160)


@pytest.fixture
async def services(settings):
    svc = build_services(settings)
    await svc.db.open()
    async with svc.db.conn() as conn:
        await conn.execute("TRUNCATE kb_jobs, kb_chunks, kb_pages, kb_documents RESTART IDENTITY CASCADE")
    yield svc
    await svc.db.close()
    await svc.http.aclose()


@asynccontextmanager
async def _client(app):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://rag") as client:
            yield client


@pytest.fixture
async def client(settings, services):
    app = create_app(settings, services=services, reranker=OverlapReranker())
    async with _client(app) as c:
        c.app = app
        yield c


async def drain(services, limit: int = 50) -> int:
    """Run the worker until the queue is empty (tests ingest synchronously)."""
    done = 0
    while done < limit and await run_once(services, "test-worker"):
        done += 1
    return done


async def upload(client, ws: int, name: str, data: bytes, **form) -> dict:
    response = await client.post(f"/v1/workspaces/{ws}/sources", headers=CRM,
                                 files=[("files", (name, data))], data={k: str(v) for k, v in form.items()})
    assert response.status_code == 202, response.text
    return response.json()["results"][0]


async def voice(client, ws: int, query: str, headers=None, **extra) -> httpx.Response:
    return await client.post("/v1/voice/retrieve", headers=headers or VOICE,
                             json={"workspaceId": ws, "query": query, **extra})
