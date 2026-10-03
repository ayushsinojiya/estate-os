"""Forward-only schema migrations, plus the embedding-model guard."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from rag_service.config import Settings

log = logging.getLogger(__name__)
MIGRATIONS = Path(__file__).parent / "migrations"


def _render(sql: str, settings: Settings) -> str:
    ops = "vector_cosine_ops" if settings.vector_type == "vector" else "halfvec_cosine_ops"
    return (sql.replace("{vector_type}", settings.vector_type)
            .replace("{dim}", str(settings.embedding_dim)).replace("{ops}", ops))


def migrate(settings: Settings) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(settings.rag_database_url, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS kb_schema_migrations ("
                     " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        # One migrator at a time, even when several containers start together.
        conn.execute("SELECT pg_advisory_lock(7300101)")
        try:
            done = {row[0] for row in conn.execute("SELECT version FROM kb_schema_migrations")}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                if path.stem in done:
                    continue
                with conn.transaction():
                    conn.execute(_render(path.read_text(), settings))
                    conn.execute("INSERT INTO kb_schema_migrations(version) VALUES (%s)", (path.stem,))
                applied.append(path.stem)
                log.info("applied %s", path.name)
            check_embedding_model(conn, settings, claim=True)
        finally:
            conn.execute("SELECT pg_advisory_unlock(7300101)")
    return applied


def check_embedding_model(conn: psycopg.Connection, settings: Settings, claim: bool = False) -> None:
    """Refuse to mix embedding models (or dimensions) in one index."""
    wanted = f"{settings.effective_embedding_model}:{settings.embedding_dim}"
    row = conn.execute("SELECT value FROM kb_meta WHERE key='embedding'").fetchone()
    if row is None:
        if claim:
            conn.execute("INSERT INTO kb_meta(key,value) VALUES ('embedding',%s)", (wanted,))
        return
    if row[0] != wanted:
        raise RuntimeError(
            f"this knowledge index was built with {row[0]} but EMBEDDING_MODEL/EMBEDDING_DIM say "
            f"{wanted}; re-embedding into a fresh database is required, mixing would corrupt retrieval")
