"""SQL for documents, pages, chunks and jobs. Every statement is scoped by workspace_id."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg import sql

from rag_service.db import Database

LIVE = ("UPLOADED", "PARSING", "EMBEDDING", "PUBLISHED")
IN_FLIGHT = ("UPLOADED", "PARSING", "EMBEDDING")


class Duplicate(Exception):
    def __init__(self, existing: dict[str, Any]):
        super().__init__("duplicate")
        self.existing = existing


class Conflict(Exception):
    pass


@dataclass
class NewDocument:
    workspace_id: int
    file_name: str
    title: str
    mime: str
    size_bytes: int
    sha256: str
    storage_key: str
    project_id: int | None = None
    project_name: str | None = None
    locality: str | None = None
    crm_document_id: int | None = None
    crm_file_id: int | None = None
    doc_type: str | None = None
    languages: list[str] | None = None
    actor_id: int | None = None
    source_id: uuid.UUID | None = None


class Store:
    def __init__(self, db: Database, low_confidence_threshold: float = 0.6):
        self.db = db
        self.low_confidence_threshold = low_confidence_threshold

    # ---------------------------------------------------------------- documents

    async def create_version(self, doc: NewDocument, max_attempts: int = 5, *, existing_source: bool = False,
                             reindex: bool = False) -> dict[str, Any]:
        """Insert a document version and its ingest job in one transaction.

        A new source_id starts at version 1; an existing one gets the next version. Raises
        Duplicate when the same bytes are already live in this workspace — except for an explicit
        reindex, which deliberately re-processes a source's own current bytes.
        """
        async with self.db.tx() as conn:
            source_id = doc.source_id or uuid.uuid4()
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{doc.workspace_id}:{source_id}",))
            existing = await (await conn.execute(
                "SELECT * FROM kb_documents WHERE workspace_id=%s AND sha256=%s AND status <> ALL(%s)"
                " ORDER BY id DESC LIMIT 1",
                (doc.workspace_id, doc.sha256, ["FAILED", "SUPERSEDED", "DELETED"]))).fetchone()
            if existing is not None and not (reindex and existing["source_id"] == source_id):
                raise Duplicate(existing)
            version = 1
            if existing_source:
                row = await (await conn.execute(
                    "SELECT max(version) AS v FROM kb_documents WHERE workspace_id=%s AND source_id=%s",
                    (doc.workspace_id, source_id))).fetchone()
                if row is None or row["v"] is None:
                    raise LookupError("source not found")
                version = row["v"] + 1
            try:
                created = await (await conn.execute(
                    """INSERT INTO kb_documents(workspace_id, source_id, version, project_id, project_name,
                         locality, crm_document_id, crm_file_id, title, file_name, mime, size_bytes, sha256,
                         storage_key, doc_type, doc_type_source, languages, actor_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (doc.workspace_id, source_id, version, doc.project_id, doc.project_name, doc.locality,
                     doc.crm_document_id, doc.crm_file_id, doc.title, doc.file_name, doc.mime, doc.size_bytes,
                     doc.sha256, doc.storage_key, doc.doc_type or "OTHER", "crm" if doc.doc_type else "auto",
                     doc.languages or [], doc.actor_id))).fetchone()
            except psycopg.errors.UniqueViolation as exc:
                raise Conflict("duplicate content raced with another upload") from exc
            await conn.execute(
                "INSERT INTO kb_jobs(workspace_id, document_id, kind, max_attempts) VALUES (%s,%s,'INGEST',%s)",
                (doc.workspace_id, created["id"], max_attempts))
            return created

    async def document(self, document_id: int) -> dict[str, Any] | None:
        async with self.db.conn() as conn:
            return await (await conn.execute("SELECT * FROM kb_documents WHERE id=%s", (document_id,))).fetchone()

    async def set_status(self, document_id: int, status: str, *, expect: tuple[str, ...] | None = None,
                         error: str | None = None, **fields: Any) -> bool:
        """Move a document to `status`, optionally only from one of `expect`. False if it had moved on."""
        assignments = [sql.SQL("status=%s"), sql.SQL("error=%s"), sql.SQL("updated_at=now()")]
        values: list[Any] = [status, error]
        for name, value in fields.items():
            assignments.append(sql.SQL("{}=%s").format(sql.Identifier(name)))
            values.append(value)
        query = sql.SQL("UPDATE kb_documents SET {} WHERE id=%s").format(sql.SQL(", ").join(assignments))
        values.append(document_id)
        if expect:
            query = query + sql.SQL(" AND status = ANY(%s)")
            values.append(list(expect))
        async with self.db.conn() as conn:
            result = await conn.execute(query, values)
            return result.rowcount == 1

    async def save_pages(self, document: dict[str, Any], pages: list[Any]) -> None:
        async with self.db.tx() as conn:
            await conn.execute("DELETE FROM kb_pages WHERE document_id=%s", (document["id"],))
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO kb_pages(workspace_id, document_id, page_no, markdown, provider, confidence,"
                    " image_sha256, input_tokens, output_tokens) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [(document["workspace_id"], document["id"], p.page_no, p.markdown, p.provider,
                      p.confidence, p.image_sha256, p.input_tokens, p.output_tokens) for p in pages])

    async def save_chunks(self, document: dict[str, Any], chunks: list[Any], vectors: list[list[float]],
                          model: str) -> None:
        """Store chunks as PENDING: invisible to retrieval until the document publishes."""
        import numpy as np

        async with self.db.tx() as conn:
            await conn.execute("DELETE FROM kb_chunks WHERE document_id=%s", (document["id"],))
            async with conn.cursor() as cur:
                await cur.executemany(
                    """INSERT INTO kb_chunks(workspace_id, project_id, document_id, doc_type, language, page_from,
                         page_to, section_path, chunk_type, ordinal, content, context_header, embedding,
                         embedding_model, tsv, token_count, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                         to_tsvector('simple', %s), %s, 'PENDING')""",
                    [(document["workspace_id"], document["project_id"], document["id"], document["doc_type"],
                      c.language, c.page_from, c.page_to, c.section_path, c.chunk_type, c.ordinal, c.content,
                      c.context_header, np.asarray(v, dtype=np.float32), model,
                      f"{c.context_header} {c.content}", c.token_count) for c, v in zip(chunks, vectors)])

    async def publish(self, document_id: int) -> bool:
        """Make a fully embedded version live, atomically replacing any older version.

        Retrieval sees either the old chunks or the new ones, never both and never neither. A
        version that was unpublished, deleted or overtaken by a newer upload while it was being
        processed is not published.
        """
        async with self.db.tx() as conn:
            doc = await (await conn.execute("SELECT * FROM kb_documents WHERE id=%s", (document_id,))).fetchone()
            if doc is None:
                return False
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                               (f"{doc['workspace_id']}:{doc['source_id']}",))
            doc = await (await conn.execute("SELECT * FROM kb_documents WHERE id=%s FOR UPDATE",
                                            (document_id,))).fetchone()
            if doc["status"] != "EMBEDDING":
                return False
            newer = await (await conn.execute(
                "SELECT 1 FROM kb_documents WHERE workspace_id=%s AND source_id=%s AND version>%s"
                " AND status <> ALL(%s)", (doc["workspace_id"], doc["source_id"], doc["version"],
                                           ["FAILED", "DELETED", "SUPERSEDED"]))).fetchone()
            if newer is not None:
                await conn.execute("DELETE FROM kb_chunks WHERE document_id=%s", (document_id,))
                await conn.execute("UPDATE kb_documents SET status='SUPERSEDED', updated_at=now() WHERE id=%s",
                                   (document_id,))
                return False
            older = [r["id"] for r in await (await conn.execute(
                "SELECT id FROM kb_documents WHERE workspace_id=%s AND source_id=%s AND version<%s"
                " AND status <> ALL(%s) FOR UPDATE",
                (doc["workspace_id"], doc["source_id"], doc["version"], ["SUPERSEDED", "DELETED"]))).fetchall()]
            if older:
                await conn.execute("DELETE FROM kb_chunks WHERE document_id = ANY(%s)", (older,))
                await conn.execute("UPDATE kb_documents SET status='SUPERSEDED', updated_at=now()"
                                   " WHERE id = ANY(%s)", (older,))
                await conn.execute("UPDATE kb_jobs SET status='CANCELLED', updated_at=now()"
                                   " WHERE document_id = ANY(%s) AND status IN ('QUEUED','RUNNING')", (older,))
            count = await conn.execute("UPDATE kb_chunks SET status='PUBLISHED' WHERE document_id=%s",
                                       (document_id,))
            await conn.execute("UPDATE kb_documents SET status='PUBLISHED', published_at=now(), chunk_count=%s,"
                               " updated_at=now() WHERE id=%s", (count.rowcount, document_id))
            return True

    async def _versions_for_update(self, conn: psycopg.AsyncConnection, workspace_id: int,
                                   source_id: uuid.UUID) -> list[dict[str, Any]]:
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{workspace_id}:{source_id}",))
        return await (await conn.execute(
            "SELECT * FROM kb_documents WHERE workspace_id=%s AND source_id=%s ORDER BY version FOR UPDATE",
            (workspace_id, source_id))).fetchall()

    async def unpublish(self, workspace_id: int, source_id: uuid.UUID) -> dict[str, Any]:
        """Remove a source from retrieval immediately, in this transaction."""
        async with self.db.tx() as conn:
            versions = await self._versions_for_update(conn, workspace_id, source_id)
            if not versions or all(v["status"] == "DELETED" for v in versions):
                raise LookupError("source not found")
            ids = [v["id"] for v in versions if v["status"] in LIVE]
            if ids:
                await conn.execute("UPDATE kb_chunks SET status='UNPUBLISHED' WHERE document_id = ANY(%s)", (ids,))
                await conn.execute("UPDATE kb_documents SET status='UNPUBLISHED', updated_at=now()"
                                   " WHERE id = ANY(%s)", (ids,))
                await conn.execute("UPDATE kb_jobs SET status='CANCELLED', updated_at=now()"
                                   " WHERE document_id = ANY(%s) AND status IN ('QUEUED','RUNNING')", (ids,))
        return await self.source(workspace_id, source_id)

    async def republish(self, workspace_id: int, source_id: uuid.UUID) -> dict[str, Any]:
        """Bring an unpublished source back. A version that never finished embedding is re-ingested."""
        async with self.db.tx() as conn:
            versions = await self._versions_for_update(conn, workspace_id, source_id)
            latest = next((v for v in reversed(versions) if v["status"] not in ("DELETED", "SUPERSEDED")), None)
            if latest is None:
                raise LookupError("source not found")
            if latest["status"] == "PUBLISHED":
                pass
            elif latest["status"] == "UNPUBLISHED" and latest["chunk_count"] > 0:
                await conn.execute("UPDATE kb_chunks SET status='PUBLISHED' WHERE document_id=%s", (latest["id"],))
                await conn.execute("UPDATE kb_documents SET status='PUBLISHED', updated_at=now() WHERE id=%s",
                                   (latest["id"],))
            elif latest["status"] in ("UNPUBLISHED", "FAILED"):
                await self._requeue(conn, latest)
            else:
                raise Conflict("this source is still being processed")
        return await self.source(workspace_id, source_id)

    async def _requeue(self, conn: psycopg.AsyncConnection, document: dict[str, Any]) -> None:
        await conn.execute("UPDATE kb_documents SET status='UPLOADED', error=NULL, updated_at=now() WHERE id=%s",
                           (document["id"],))
        await conn.execute(
            "INSERT INTO kb_jobs(workspace_id, document_id, kind) VALUES (%s,%s,'INGEST')"
            " ON CONFLICT (document_id, kind) WHERE status IN ('QUEUED','RUNNING') DO NOTHING",
            (document["workspace_id"], document["id"]))

    async def retry(self, workspace_id: int, source_id: uuid.UUID) -> dict[str, Any]:
        async with self.db.tx() as conn:
            versions = await self._versions_for_update(conn, workspace_id, source_id)
            latest = next((v for v in reversed(versions) if v["status"] != "SUPERSEDED"), None)
            if latest is None or latest["status"] == "DELETED":
                raise LookupError("source not found")
            if latest["status"] != "FAILED":
                raise Conflict("only a failed source can be retried")
            await self._requeue(conn, latest)
        return await self.source(workspace_id, source_id)

    async def delete(self, workspace_id: int, source_id: uuid.UUID) -> list[str]:
        """Delete every version; chunks go in the same transaction. Returns storage keys to remove."""
        async with self.db.tx() as conn:
            versions = await self._versions_for_update(conn, workspace_id, source_id)
            if not versions or all(v["status"] == "DELETED" for v in versions):
                raise LookupError("source not found")
            ids = [v["id"] for v in versions]
            await conn.execute("DELETE FROM kb_chunks WHERE document_id = ANY(%s)", (ids,))
            await conn.execute("UPDATE kb_jobs SET status='CANCELLED', updated_at=now()"
                               " WHERE document_id = ANY(%s) AND status IN ('QUEUED','RUNNING')", (ids,))
            await conn.execute("UPDATE kb_documents SET status='DELETED', updated_at=now() WHERE id = ANY(%s)", (ids,))
            return [v["storage_key"] for v in versions]

    # ---------------------------------------------------------------- reads

    async def source(self, workspace_id: int, source_id: uuid.UUID) -> dict[str, Any]:
        async with self.db.conn() as conn:
            versions = await (await conn.execute(
                "SELECT * FROM kb_documents WHERE workspace_id=%s AND source_id=%s ORDER BY version DESC",
                (workspace_id, source_id))).fetchall()
            if not versions or versions[0]["status"] == "DELETED":
                raise LookupError("source not found")
            current = versions[0]
            pages = await (await conn.execute(
                "SELECT page_no, provider, confidence FROM kb_pages WHERE document_id=%s ORDER BY page_no",
                (current["id"],))).fetchall()
        return {"current": current, "versions": versions, "pages": pages}

    async def by_crm_document(self, workspace_id: int, crm_document_id: int) -> dict[str, Any] | None:
        async with self.db.conn() as conn:
            row = await (await conn.execute(
                "SELECT source_id FROM kb_documents WHERE workspace_id=%s AND crm_document_id=%s"
                " AND status <> 'DELETED' ORDER BY id DESC LIMIT 1", (workspace_id, crm_document_id))).fetchone()
        return None if row is None else await self.source(workspace_id, row["source_id"])

    async def list_sources(self, workspace_id: int, *, page: int, size: int, search: str = "",
                           status: str = "", project_id: int | None = None,
                           date_from: datetime | None = None, date_to: datetime | None = None) -> dict[str, Any]:
        where = ["d.workspace_id=%s", "d.version = (SELECT max(version) FROM kb_documents x"
                 " WHERE x.workspace_id=d.workspace_id AND x.source_id=d.source_id)", "d.status <> 'DELETED'"]
        params: list[Any] = [workspace_id]
        if search:
            where.append("(d.title ILIKE %s OR d.file_name ILIKE %s)")
            like = "%" + search.replace("%", r"\%").replace("_", r"\_") + "%"
            params += [like, like]
        if status:
            where.append("d.status=%s")
            params.append(status)
        if project_id is not None:
            where.append("d.project_id=%s")
            params.append(project_id)
        if date_from is not None:
            where.append("d.created_at >= %s")
            params.append(date_from)
        if date_to is not None:
            where.append("d.created_at < %s")
            params.append(date_to)
        clause = " AND ".join(where)
        async with self.db.conn() as conn:
            total = (await (await conn.execute(f"SELECT count(*) AS n FROM kb_documents d WHERE {clause}",
                                               params)).fetchone())["n"]
            items = await (await conn.execute(
                f"""SELECT d.*, (SELECT count(*) FROM kb_pages p WHERE p.document_id=d.id AND p.confidence < %s)
                      AS low_confidence_pages
                    FROM kb_documents d WHERE {clause} ORDER BY d.created_at DESC, d.id DESC
                    LIMIT %s OFFSET %s""", [self.low_confidence_threshold] + params + [size, page * size])).fetchall()
        return {"items": items, "total": total, "page": page, "size": size}

    # ---------------------------------------------------------------- jobs

    async def claim_job(self, worker: str) -> dict[str, Any] | None:
        async with self.db.tx() as conn:
            job = await (await conn.execute(
                """SELECT * FROM kb_jobs WHERE status='QUEUED' AND run_after <= now()
                   ORDER BY run_after, id LIMIT 1 FOR UPDATE SKIP LOCKED""")).fetchone()
            if job is None:
                return None
            await conn.execute("UPDATE kb_jobs SET status='RUNNING', attempts=attempts+1, locked_at=now(),"
                               " locked_by=%s, updated_at=now() WHERE id=%s", (worker, job["id"]))
            job["attempts"] += 1
            return job

    async def finish_job(self, job_id: int) -> None:
        async with self.db.conn() as conn:
            await conn.execute("UPDATE kb_jobs SET status='DONE', updated_at=now() WHERE id=%s", (job_id,))

    async def fail_job(self, job: dict[str, Any], error: str, backoff_s: float) -> bool:
        """Back off and retry, or give up. Returns True when the job will not run again."""
        final = job["attempts"] >= job["max_attempts"]
        async with self.db.conn() as conn:
            await conn.execute(
                "UPDATE kb_jobs SET status=%s, last_error=%s, run_after=now() + make_interval(secs => %s),"
                " updated_at=now() WHERE id=%s AND status='RUNNING'",
                ("FAILED" if final else "QUEUED", error[:1000], backoff_s * (2 ** (job["attempts"] - 1)),
                 job["id"]))
        return final

    async def reclaim_stale_jobs(self, older_than_s: int = 900) -> int:
        """A worker that died mid-job leaves it RUNNING; put it back in the queue."""
        async with self.db.conn() as conn:
            result = await conn.execute(
                "UPDATE kb_jobs SET status='QUEUED', updated_at=now() WHERE status='RUNNING'"
                " AND locked_at < now() - make_interval(secs => %s)", (older_than_s,))
            return result.rowcount
