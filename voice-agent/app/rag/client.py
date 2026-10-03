"""Knowledge retrieval for live calls: POST /v1/voice/retrieve on the knowledge service.

Bounded by RAG_TIMEOUT_MS (600 ms). On a timeout or any error the result is empty and the agent
says it will have the detail confirmed — a slow lookup must never leave the caller in silence or
tempt the model to answer from memory.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)


@dataclass
class Retrieval:
    chunks: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok | empty | timeout | error | disabled
    latency_ms: float = 0.0


class Knowledge(Protocol):
    async def retrieve(self, query: str, project_id: str | None = None, doc_types: list[str] | None = None,
                       language: str | None = None, k: int = 4) -> Retrieval: ...
    async def aclose(self) -> None: ...


class HttpKnowledge:
    def __init__(self, base_url: str, token: str, workspace_id: int, timeout_ms: int = 600,
                 client: httpx.AsyncClient | None = None):
        self.url = base_url.rstrip("/") + "/v1/voice/retrieve"
        self.workspace_id = workspace_id
        self.timeout_s = timeout_ms / 1000
        self._headers = {"Authorization": f"Bearer {token}"}
        self._http = client or httpx.AsyncClient()

    async def retrieve(self, query: str, project_id: str | None = None, doc_types: list[str] | None = None,
                       language: str | None = None, k: int = 4) -> Retrieval:
        body: dict[str, Any] = {"workspaceId": self.workspace_id, "query": query[:500], "k": k}
        if project_id:
            body["projectId"] = project_id
        if doc_types:
            body["docTypes"] = doc_types
        if language:
            body["language"] = language
        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(self._http.post(self.url, json=body, headers=self._headers),
                                              self.timeout_s)
            elapsed = (time.perf_counter() - started) * 1000
            if response.status_code != 200:
                log.warning("knowledge service %s for %r", response.status_code, query[:60])
                return Retrieval([], "error", elapsed)
            chunks = response.json().get("results", [])
            return Retrieval(chunks, "ok" if chunks else "empty", elapsed)
        except asyncio.TimeoutError:
            log.warning("knowledge lookup exceeded %.0f ms; answering without it", self.timeout_s * 1000)
            return Retrieval([], "timeout", self.timeout_s * 1000)
        except httpx.HTTPError as exc:
            log.warning("knowledge service unreachable: %r", exc)
            return Retrieval([], "error", (time.perf_counter() - started) * 1000)

    async def aclose(self) -> None:
        await self._http.aclose()


class FakeKnowledge:
    """Canned brochure facts for the mock CRM's projects, for offline mode and tests."""

    DOCS = [
        {"documentId": "901", "projectId": "11", "title": "Sahyadri Grove brochure", "docType": "BROCHURE", "page": 4,
         "sectionPath": "Amenities > Clubhouse",
         "content": "A 14,000 sq ft clubhouse with a rooftop infinity pool, a gym and a yoga deck."},
        {"documentId": "902", "projectId": "11", "title": "Sahyadri Grove FAQ", "docType": "FAQ", "page": 1,
         "sectionPath": "", "content": "Q: Are pets allowed?\nA: Yes, pets are welcome; there is a pet park."},
        {"documentId": "903", "projectId": "11", "title": "Sahyadri Grove charges", "docType": "PRICE_SHEET",
         "page": 1, "sectionPath": "Payment plan",
         "content": "Stage: On booking; Percent: 10%. Stage: Agreement; Percent: 10%. Floor rise: ₹40 per sq ft per floor."},
        {"documentId": "904", "projectId": "12", "title": "Mula Vista brochure", "docType": "BROCHURE", "page": 2,
         "sectionPath": "Location", "content": "Mula Vista is five minutes from EON IT Park in Kharadi."},
    ]

    async def retrieve(self, query: str, project_id: str | None = None, doc_types: list[str] | None = None,
                       language: str | None = None, k: int = 4) -> Retrieval:
        words = {w for w in query.lower().replace("?", " ").split() if len(w) > 2}
        scored = []
        for doc in self.DOCS:
            if project_id and doc["projectId"] != str(project_id):
                continue
            if doc_types and doc["docType"] not in doc_types:
                continue
            text = (doc["content"] + " " + doc["sectionPath"] + " " + doc["title"]).lower()
            score = sum(1 for w in words if w in text)
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda pair: -pair[0])
        chunks = [{**doc, "score": float(score)} for score, doc in scored[:k]]
        return Retrieval(chunks, "ok" if chunks else "empty", 1.0)

    async def aclose(self) -> None:
        return None
