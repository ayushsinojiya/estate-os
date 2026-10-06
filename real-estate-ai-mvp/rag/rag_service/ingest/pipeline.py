"""One document version, from stored bytes to published chunks.

UPLOADED → PARSING → EMBEDDING → PUBLISHED, or FAILED. Each step re-checks the document's status,
so a version that was unpublished, deleted or replaced while it was being processed stops there
instead of overwriting the newer state.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from rag_service.ingest.chunk import ChunkConfig, DocContext, chunk_document
from rag_service.ingest.classify import classify, languages_of
from rag_service.ingest.files import UnsupportedFile, detect
from rag_service.ingest.parse import parse_document
from rag_service.services import Services

log = logging.getLogger(__name__)


class PermanentIngestError(Exception):
    """Retrying cannot help: the file is unreadable or has no text."""


def chunk_config(settings) -> ChunkConfig:
    return ChunkConfig(target_tokens=settings.chunk_target_tokens, max_tokens=settings.chunk_max_tokens,
                       min_tokens=settings.chunk_min_tokens, overlap_ratio=settings.chunk_overlap_ratio,
                       table_max_tokens=settings.table_max_tokens,
                       table_row_min_rows=settings.table_row_chunk_min_rows)


async def ingest(services: Services, document_id: int) -> str:
    s, store = services.settings, services.store
    doc = await store.document(document_id)
    if doc is None or doc["status"] not in ("UPLOADED", "PARSING", "EMBEDDING"):
        return "SKIPPED"
    if not await store.set_status(document_id, "PARSING", expect=("UPLOADED", "PARSING", "EMBEDDING")):
        return "SKIPPED"

    data = services.files.read(doc["storage_key"])
    try:
        kind = detect(doc["file_name"], data).kind
    except UnsupportedFile as exc:
        raise PermanentIngestError(str(exc)) from exc
    pages = await parse_document(kind, data, services.parser, dpi=s.parse_dpi,
                                 concurrency=s.parse_concurrency)
    await store.save_pages(doc, pages)
    texts = [p.markdown for p in pages]
    if not any(t.strip() for t in texts):
        raise PermanentIngestError("no text could be extracted from this file")

    if doc["doc_type_source"] == "crm":
        doc_type, languages = doc["doc_type"], doc["languages"] or languages_of("\n\n".join(texts))
    else:
        doc_type, languages = await classify(doc["file_name"], texts, services.json_model)

    ctx = DocContext(doc_type=doc_type, project_name=doc["project_name"], locality=doc["locality"],
                     paged=kind in ("pdf", "image", "pptx"))
    chunks = chunk_document([(p.page_no, p.markdown) for p in pages], ctx, chunk_config(s))
    if not chunks:
        raise PermanentIngestError("the document produced no searchable text")

    parse_in = sum(p.input_tokens for p in pages)
    parse_out = sum(p.output_tokens for p in pages)
    if not await store.set_status(document_id, "EMBEDDING", expect=("PARSING",), doc_type=doc_type,
                                  languages=languages, page_count=len(pages), parse_input_tokens=parse_in,
                                  parse_output_tokens=parse_out):
        return "SKIPPED"

    result = await services.embedder.embed([c.embedding_text for c in chunks])
    doc = await store.document(document_id)
    await store.save_chunks(doc, chunks, result.vectors, services.embedder.model)
    cost = (Decimal(parse_in) * Decimal(str(s.price_parse_input_per_m))
            + Decimal(parse_out) * Decimal(str(s.price_parse_output_per_m))
            + Decimal(result.tokens) * Decimal(str(s.price_embed_per_m))) / Decimal(1_000_000)
    await store.set_status(document_id, "EMBEDDING", expect=("EMBEDDING",), embed_tokens=result.tokens,
                           cost_usd=cost, embedding_model=services.embedder.model)
    published = await store.publish(document_id)
    if published:
        await store.queue_extraction(doc)
    log.info("document %s (%s v%s): %d pages, %d chunks, %s", document_id, doc["file_name"], doc["version"],
             len(pages), len(chunks), "published" if published else "not published (superseded or withdrawn)")
    return "PUBLISHED" if published else "SKIPPED"
