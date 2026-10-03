"""Connection pool. pgvector types are registered on every new connection."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from rag_service.config import Settings


async def _configure(conn: psycopg.AsyncConnection) -> None:
    await register_vector_async(conn)
    conn.row_factory = dict_row
    await conn.set_autocommit(True)
    # Filtered HNSW searches can return fewer rows than asked for; pgvector >= 0.8 keeps scanning
    # until the filter is satisfied. Older pgvector ignores the setting's absence harmlessly.
    for statement in ("SET hnsw.ef_search = 100", "SET hnsw.iterative_scan = relaxed_order",
                      "SET pg_trgm.word_similarity_threshold = 0.5"):
        try:
            await conn.execute(statement)
        except psycopg.Error:
            pass


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool = AsyncConnectionPool(settings.rag_database_url, min_size=settings.db_pool_min,
                                        max_size=settings.db_pool_max, configure=_configure,
                                        open=False, kwargs={"prepare_threshold": None})

    async def open(self) -> None:
        await self.pool.open(wait=True, timeout=30)

    async def close(self) -> None:
        await self.pool.close()

    @asynccontextmanager
    async def conn(self) -> AsyncIterator[psycopg.AsyncConnection]:
        async with self.pool.connection() as conn:
            yield conn

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[psycopg.AsyncConnection]:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                yield conn
