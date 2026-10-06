"""Background ingestion worker. Any number may run; jobs are claimed with SKIP LOCKED."""

from __future__ import annotations

import asyncio
import logging
import os
import socket

from rag_service.extract import extract
from rag_service.ingest.pipeline import PermanentIngestError, ingest
from rag_service.services import Services

log = logging.getLogger(__name__)


async def run_extraction(services: Services, document_id: int) -> None:
    """Projects and listings in a published document, for the CRM's Projects & inventory."""
    doc = await services.store.document(document_id)
    if doc is None or doc["status"] != "PUBLISHED":
        return  # replaced or withdrawn meanwhile: the CRM reads the current version instead
    result = await extract(await services.store.pages_of(document_id), doc["file_name"],
                           services.extraction_model)
    await services.store.save_extraction(document_id, result)
    log.info("document %s (%s v%s): extracted %d project(s), %d listing(s) with %d model call(s)",
             document_id, doc["file_name"], doc["version"], len(result["projects"]), len(result["listings"]),
             result["modelCalls"])


async def run_once(services: Services, worker: str) -> bool:
    """Process one due job. Returns False when the queue was empty."""
    store = services.store
    job = await store.claim_job(worker)
    if job is None:
        return False
    if job["kind"] == "EXTRACT":
        try:
            await run_extraction(services, job["document_id"])
        except Exception as exc:  # noqa: BLE001 - e.g. rate limited: back off and retry
            log.exception("extraction of document %s failed (attempt %d)", job["document_id"], job["attempts"])
            if await store.fail_job(job, repr(exc), services.settings.job_backoff_s):
                await store.save_extraction(job["document_id"], None, f"gave up: {exc!r}")
        else:
            await store.finish_job(job["id"])
        return True
    try:
        await ingest(services, job["document_id"])
    except PermanentIngestError as exc:
        log.warning("document %s cannot be ingested: %s", job["document_id"], exc)
        await store.finish_job(job["id"])
        await store.set_status(job["document_id"], "FAILED", expect=("UPLOADED", "PARSING", "EMBEDDING"),
                               error=str(exc)[:500])
    except Exception as exc:  # noqa: BLE001 - transient: back off and retry
        log.exception("ingest of document %s failed (attempt %d)", job["document_id"], job["attempts"])
        final = await store.fail_job(job, repr(exc), services.settings.job_backoff_s)
        if final:
            await store.set_status(job["document_id"], "FAILED", expect=("UPLOADED", "PARSING", "EMBEDDING"),
                                   error=f"gave up after {job['attempts']} attempts: {exc!r}"[:500])
        else:
            await store.set_status(job["document_id"], "UPLOADED", expect=("PARSING", "EMBEDDING"),
                                   error=f"retrying: {exc!r}"[:500])
    else:
        await store.finish_job(job["id"])
    return True


async def run(services: Services, stop: asyncio.Event | None = None) -> None:
    worker = f"{socket.gethostname()}-{os.getpid()}"
    stop = stop or asyncio.Event()
    last_reclaim = 0.0
    loop = asyncio.get_running_loop()
    log.info("worker %s started", worker)
    while not stop.is_set():
        if loop.time() - last_reclaim > 60:
            reclaimed = await services.store.reclaim_stale_jobs()
            if reclaimed:
                log.warning("re-queued %d jobs left running by a dead worker", reclaimed)
            last_reclaim = loop.time()
        try:
            busy = await run_once(services, worker)
        except Exception:  # noqa: BLE001 - e.g. database briefly unavailable
            log.exception("worker loop error")
            busy = False
        if not busy:
            try:
                await asyncio.wait_for(stop.wait(), services.settings.worker_poll_s)
            except asyncio.TimeoutError:
                pass
