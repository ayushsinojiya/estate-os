"""Hybrid candidate retrieval: vector, keyword and name-similarity lists fused by RRF.

Every query is scoped by workspace_id and status='PUBLISHED' in SQL. A project scope also admits
workspace-wide documents (project_id IS NULL), since a builder's general FAQ applies to every
project. The three lists run concurrently on separate pooled connections.
"""

from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from psycopg import sql

from rag_service.db import Database
from rag_service.providers.embeddings import Embedder

_TOKEN = re.compile(r"[0-9a-zऀ-ॿ઀-૿]+", re.I)
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "of", "for", "to", "in", "on", "at", "and", "or", "what", "which",
    "how", "much", "many", "does", "do", "is", "it", "this", "that", "there", "any", "me", "tell", "about",
    "you", "your", "i", "my", "we", "can", "be", "with", "by", "from", "please",
}

_COLUMNS = """c.id, c.document_id, c.project_id, c.doc_type, c.language, c.page_from, c.page_to,
  c.section_path, c.chunk_type, c.content, c.context_header, d.title, d.source_id, d.crm_document_id,
  d.workspace_id"""


@dataclass
class Candidate:
    id: int
    row: dict[str, Any]
    score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)
    rerank_score: float | None = None


@dataclass
class Scope:
    workspace_id: int
    project_id: int | None = None
    doc_types: list[str] | None = None
    crm_document_ids: list[int] | None = None  # allowlist; None means no allowlist


def tsquery(text: str) -> str | None:
    tokens = []
    for token in _TOKEN.findall(text.lower()):
        if token in _STOPWORDS or (len(token) < 2 and not token.isdigit()):
            continue
        if token not in tokens:
            tokens.append(token)
    if not tokens:
        return None
    # Words match by prefix (charge → charges); codes and numbers (RERA ids) match exactly.
    return " | ".join(f"{t}:*" if len(t) >= 4 and t.isalpha() else t for t in tokens[:24])


def normalize_query(text: str) -> str:
    return " ".join(text.lower().split())


def _filters(scope: Scope, params: dict[str, Any]) -> str:
    clauses = ["c.workspace_id = %(ws)s", "c.status = 'PUBLISHED'"]
    params["ws"] = scope.workspace_id
    if scope.project_id is not None:
        clauses.append("(c.project_id = %(project)s OR c.project_id IS NULL)")
        params["project"] = scope.project_id
    if scope.doc_types:
        clauses.append("c.doc_type = ANY(%(types)s)")
        params["types"] = scope.doc_types
    if scope.crm_document_ids is not None:
        clauses.append("d.crm_document_id = ANY(%(allow)s)")
        params["allow"] = scope.crm_document_ids
    return " AND ".join(clauses)


class Searcher:
    def __init__(self, db: Database, embedder: Embedder, cache_size: int = 2048, pool: int = 30):
        self.db = db
        self.embedder = embedder
        self.pool = pool
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.cache_size = cache_size

    async def embed_queries(self, queries: list[str]) -> list[np.ndarray]:
        """Embed with an LRU cache keyed on the normalised query (callers repeat themselves)."""
        keys = [normalize_query(q) for q in queries]
        missing = [k for k in dict.fromkeys(keys) if k not in self._cache]
        if missing:
            result = await self.embedder.embed(missing)
            for key, vector in zip(missing, result.vectors):
                self._cache[key] = np.asarray(vector, dtype=np.float32)
                if len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        out = []
        for key in keys:
            self._cache.move_to_end(key)
            out.append(self._cache[key])
        return out

    async def _vector(self, conn, scope: Scope, vector: np.ndarray) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"q": vector, "n": self.pool}
        where = _filters(scope, params)
        return await (await conn.execute(
            f"""SELECT * FROM (SELECT {_COLUMNS}, c.embedding <=> %(q)s AS distance
                  FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
                  WHERE {where} ORDER BY c.embedding <=> %(q)s LIMIT %(n)s) v ORDER BY distance""",
            params)).fetchall()

    async def _keyword(self, conn, scope: Scope, query: str) -> list[dict[str, Any]]:
        tsq = tsquery(query)
        if tsq is None:
            return []
        params: dict[str, Any] = {"tsq": tsq, "n": self.pool}
        where = _filters(scope, params)
        return await (await conn.execute(
            f"""SELECT {_COLUMNS}, ts_rank_cd(c.tsv, q, 32) AS rank
                FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id,
                     to_tsquery('simple', %(tsq)s) q
                WHERE {where} AND c.tsv @@ q ORDER BY rank DESC, c.id LIMIT %(n)s""",
            params)).fetchall()

    async def _names(self, conn, scope: Scope, query: str) -> list[dict[str, Any]]:
        """Project names and RERA numbers, spelled loosely by a caller or a speech recogniser."""
        params: dict[str, Any] = {"q": query, "n": 10}
        where = _filters(scope, params)
        return await (await conn.execute(
            f"""SELECT {_COLUMNS}, word_similarity(%(q)s, c.context_header) AS sim
                FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
                WHERE {where} AND %(q)s <%% c.context_header
                ORDER BY sim DESC, c.id LIMIT %(n)s""", params)).fetchall()

    async def candidates(self, scope: Scope, queries: list[str],
                         vectors: list[np.ndarray]) -> list[list[dict[str, Any]]]:
        """[vector, keyword, names] lists for every query, all read from ONE database snapshot.

        The three searches run concurrently on three connections. Without a shared snapshot they
        could straddle a publish commit and return chunks of the old and the new version together;
        so the first connection exports its snapshot and the other two import it.
        """
        pool = self.db.pool
        async with pool.connection() as a, pool.connection() as b, pool.connection() as c:
            conns = (a, b, c)
            for conn in conns:
                await conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                snapshot = (await (await a.execute("SELECT pg_export_snapshot() AS s")).fetchone())["s"]
                statement = sql.SQL("SET TRANSACTION SNAPSHOT {}").format(sql.Literal(snapshot))
                await asyncio.gather(b.execute(statement), c.execute(statement))

                async def each(fn, conn, args_per_query):
                    return [await fn(conn, scope, arg) for arg in args_per_query]

                vector_lists, keyword_lists, name_lists = await asyncio.gather(
                    each(self._vector, a, vectors), each(self._keyword, b, queries), each(self._names, c, queries))
            finally:
                for conn in conns:
                    await conn.execute("ROLLBACK")
        out: list[list[dict[str, Any]]] = []
        for v, k, n in zip(vector_lists, keyword_lists, name_lists):
            out += [v, k, n]
        return out


def rrf(ranked_lists: list[list[dict[str, Any]]], k: int = 60, names: list[str] | None = None) -> list[Candidate]:
    """Reciprocal Rank Fusion: each list contributes 1 / (k + rank) for every item it ranks."""
    fused: dict[int, Candidate] = {}
    for index, rows in enumerate(ranked_lists):
        label = names[index] if names and index < len(names) else str(index)
        for rank, row in enumerate(rows, start=1):
            candidate = fused.setdefault(row["id"], Candidate(row["id"], row))
            candidate.score += 1.0 / (k + rank)
            candidate.ranks[label] = rank
    return sorted(fused.values(), key=lambda c: (-c.score, c.id))
