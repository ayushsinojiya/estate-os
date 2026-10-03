"""HTTP API of the knowledge service.

Two callers, two tokens:

- the CRM (RAG_SERVICE_TOKEN) manages sources and searches on behalf of an authorised user; it
  has already checked workspace membership before calling;
- the voice agent (RAG_VOICE_TOKEN) may only call /v1/voice/retrieve, and only for the one
  workspace that token is bound to (RAG_VOICE_WORKSPACE_ID).
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_service.config import Settings, get_settings
from rag_service.ingest.files import UnsupportedFile, detect, safe_name, sha256
from rag_service.retrieve import rerank as rerank_mod
from rag_service.retrieve.retriever import Retriever
from rag_service.retrieve.search import Scope, Searcher
from rag_service.retrieve.snippet import focus
from rag_service.services import Services, build_services
from rag_service.store import Conflict, Duplicate, NewDocument

log = logging.getLogger("rag_service")

DOC_TYPES = {"BROCHURE", "PRICE_SHEET", "PAYMENT_PLAN", "FAQ", "RERA", "LEGAL", "FLOOR_PLAN", "OTHER"}
LANGS = {"en", "hi", "mr", "gu"}


# ---------------------------------------------------------------- serialisation


def _iso(value: Any) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _id(value: Any) -> str | None:
    return None if value is None else str(value)


def source_json(doc: dict[str, Any], pages: list[dict[str, Any]] | None = None, threshold: float = 0.6,
                versions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    low = [p["page_no"] for p in pages or [] if p["confidence"] < threshold]
    out = {
        "id": str(doc["source_id"]), "version": doc["version"], "workspaceId": _id(doc["workspace_id"]),
        "projectId": _id(doc["project_id"]), "crmDocumentId": _id(doc["crm_document_id"]),
        "crmFileId": _id(doc["crm_file_id"]), "title": doc["title"], "fileName": doc["file_name"],
        "mime": doc["mime"], "sizeBytes": doc["size_bytes"], "sha256": doc["sha256"],
        "docType": doc["doc_type"], "languages": list(doc["languages"] or []), "status": doc["status"],
        "error": doc["error"], "pageCount": doc["page_count"], "chunkCount": doc["chunk_count"],
        "embeddingModel": doc["embedding_model"], "costUsd": float(doc["cost_usd"]),
        "createdAt": _iso(doc["created_at"]), "updatedAt": _iso(doc["updated_at"]),
        "publishedAt": _iso(doc["published_at"]),
    }
    if pages is not None:
        out["lowConfidencePages"] = low
        out["pages"] = [{"page": p["page_no"], "provider": p["provider"], "confidence": round(p["confidence"], 2)}
                        for p in pages]
    elif "low_confidence_pages" in doc:
        out["lowConfidencePageCount"] = doc["low_confidence_pages"]
    out["warnings"] = ([f"{len(low)} page(s) were parsed with low confidence; check pages {low}"] if low else [])
    if versions is not None:
        out["versions"] = [{"version": v["version"], "status": v["status"], "createdAt": _iso(v["created_at"])}
                           for v in versions]
    return out


def status_json(source: dict[str, Any] | None, workspace_id: int, crm_document_id: int,
                threshold: float) -> dict[str, Any]:
    if source is None:
        return {"documentId": str(crm_document_id), "workspaceId": str(workspace_id), "status": "NOT_INDEXED"}
    current = source["current"]
    published = next((v["version"] for v in source["versions"] if v["status"] == "PUBLISHED"), None)
    body = source_json(current, source["pages"], threshold)
    body.update({"documentId": str(crm_document_id), "sourceId": str(current["source_id"]),
                 "publishedVersion": published, "searchable": published is not None})
    body.pop("id", None)
    return body


# ---------------------------------------------------------------- request models


def _int_id(value: Any, name: str) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive integer") from None
    if number < 1:
        raise ValueError(f"{name} must be a positive integer")
    return number


class VoiceRetrieve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspaceId: int
    projectId: int | None = None
    query: str = Field(min_length=1, max_length=500)
    docTypes: list[str] | None = None
    language: str | None = None
    k: int = Field(default=4, ge=1, le=10)

    @field_validator("workspaceId", "projectId", mode="before")
    @classmethod
    def _ids(cls, value: Any, info) -> Any:
        return None if value in (None, "") and info.field_name == "projectId" else _int_id(value, info.field_name)

    @field_validator("docTypes")
    @classmethod
    def _types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        bad = [v for v in value if v not in DOC_TYPES]
        if bad:
            raise ValueError(f"unknown docTypes {bad}")
        return value or None


class KnowledgeSearch(BaseModel):
    model_config = ConfigDict(extra="ignore")  # the CRM forwards its whole recommendation request
    workspaceId: int
    projectId: int | None = None
    query: str = Field(min_length=1, max_length=2000)
    language: str = "en"
    publishedDocumentIds: list[int]
    k: int = Field(default=5, ge=1, le=20)

    @field_validator("workspaceId", "projectId", mode="before")
    @classmethod
    def _ids(cls, value: Any, info) -> Any:
        return None if value in (None, "") and info.field_name == "projectId" else _int_id(value, info.field_name)

    @field_validator("publishedDocumentIds", mode="before")
    @classmethod
    def _allow(cls, value: Any) -> list[int]:
        if not isinstance(value, list):
            raise ValueError("publishedDocumentIds is required")
        return [_int_id(v, "publishedDocumentIds") for v in value]


# ---------------------------------------------------------------- app


def create_app(settings: Settings | None = None, services: Services | None = None,
               reranker: rerank_mod.Reranker | None | str = "auto") -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = services or build_services(settings)
        await svc.db.open()
        async with svc.db.conn() as conn:
            row = await (await conn.execute("SELECT value FROM kb_meta WHERE key='embedding'")).fetchone()
        wanted = f"{settings.effective_embedding_model}:{settings.embedding_dim}"
        if row is not None and row["value"] != wanted:
            raise RuntimeError(f"knowledge index was built with {row['value']}, configured {wanted}")
        chosen = reranker
        if chosen == "auto":
            chosen = await _build_reranker(settings, svc)
        app.state.services = svc
        app.state.retriever = Retriever(settings, Searcher(svc.db, svc.embedder, settings.query_cache_size,
                                                           settings.candidate_pool), chosen, svc.json_model)
        yield
        await svc.db.close()
        await svc.http.aclose()

    app = FastAPI(title="EstraOS knowledge service", lifespan=lifespan)

    @app.exception_handler(ValueError)
    async def _bad(_request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def svc_dep(request: Request) -> Services:
        return request.app.state.services

    def bearer(authorization: str) -> str:
        return authorization[7:] if authorization.lower().startswith("bearer ") else ""

    def crm(authorization: str = Header(default="")) -> None:
        token = bearer(authorization)
        if not settings.rag_service_token or not hmac.compare_digest(token, settings.rag_service_token):
            raise HTTPException(401, "unauthorised")

    def actor(x_actor_id: str | None = Header(default=None)) -> int | None:
        return int(x_actor_id) if x_actor_id and x_actor_id.isdigit() else None

    # ---- health

    @app.get("/healthz")
    async def healthz(request: Request) -> dict:
        svc: Services = request.app.state.services
        async with svc.db.conn() as conn:
            await conn.execute("SELECT 1")
            jobs = await (await conn.execute(
                "SELECT status, count(*) AS n FROM kb_jobs WHERE status IN ('QUEUED','RUNNING') GROUP BY status"
            )).fetchall()
        retriever: Retriever = request.app.state.retriever
        return {"status": "ok", "providerMode": settings.provider_mode,
                "embeddingModel": settings.effective_embedding_model, "embeddingDim": settings.embedding_dim,
                "parser": svc.parser.name if svc.parser else "text-layer-only",
                "reranker": retriever.reranker.name if retriever.reranker else "none",
                "jobs": {r["status"]: r["n"] for r in jobs}}

    # ---- live-call retrieval

    @app.post("/v1/voice/retrieve")
    async def voice_retrieve(body: VoiceRetrieve, request: Request,
                             authorization: str = Header(default="")) -> dict:
        token = bearer(authorization)
        if settings.rag_voice_token and hmac.compare_digest(token, settings.rag_voice_token):
            if body.workspaceId != settings.rag_voice_workspace_id:
                raise HTTPException(403, "this token is not valid for that workspace")
        elif not (settings.rag_service_token and hmac.compare_digest(token, settings.rag_service_token)):
            raise HTTPException(401, "unauthorised")
        retriever: Retriever = request.app.state.retriever
        result = await retriever.run(Scope(body.workspaceId, body.projectId, body.docTypes), body.query, body.k,
                                     rewrite_query=settings.rewrite_on_voice,
                                     embed_budget_ms=settings.voice_embed_budget_ms)
        limit = settings.voice_snippet_chars
        return {
            "workspaceId": str(body.workspaceId), "projectId": _id(body.projectId), "query": body.query,
            # Prices, availability and BHK counts always come from the CRM, never from these chunks.
            "inventoryAuthoritative": "crm",
            "results": [{
                "documentId": _id(c.row["crm_document_id"]) or str(c.row["source_id"]),
                "sourceId": str(c.row["source_id"]), "title": c.row["title"], "docType": c.row["doc_type"],
                "page": c.row["page_from"], "pageTo": c.row["page_to"], "sectionPath": c.row["section_path"],
                "chunkType": c.row["chunk_type"], "language": c.row["language"],
                "score": round(c.rerank_score if c.rerank_score is not None else c.score, 4),
                "content": focus(c.row["content"], body.query, limit, c.row["chunk_type"])}
                for c in result.items],
            "rerank": result.rerank, "vector": result.vector, "timingsMs": result.timings_ms,
        }

    # ---- CRM search (contract of RestRagServiceClient / IntegrationPayloads.publishedSearch)

    @app.post("/v1/knowledge/search", dependencies=[Depends(crm)])
    async def knowledge_search(body: KnowledgeSearch, request: Request) -> dict:
        if not body.publishedDocumentIds:
            return {"results": [], "inventoryAuthoritative": "crm", "queries": []}
        retriever: Retriever = request.app.state.retriever
        scope = Scope(body.workspaceId, body.projectId, crm_document_ids=body.publishedDocumentIds)
        result = await retriever.run(scope, body.query, body.k, rewrite_query=True)
        return {
            "results": [{
                "workspaceId": str(c.row["workspace_id"]), "projectId": _id(c.row["project_id"]),
                "documentId": str(c.row["crm_document_id"]), "status": "PUBLISHED",
                "language": c.row["language"] or "en", "text": c.row["content"],
                "pageReference": _id(c.row["page_from"]) or "", "sectionPath": c.row["section_path"],
                "title": c.row["title"],
                "score": round(c.rerank_score if c.rerank_score is not None else c.score, 4)}
                for c in result.items],
            "inventoryAuthoritative": "crm", "queries": result.queries, "rerank": result.rerank,
        }

    # ---- sources (CRM Documents/Files uploads)

    async def _store_upload(svc: Services, ws: int, upload: UploadFile, *, source_id: uuid.UUID | None,
                            meta: dict[str, Any], actor_id: int | None) -> dict[str, Any]:
        name = safe_name(upload.filename)
        data = await upload.read(settings.rag_max_upload_bytes + 1)
        if len(data) > settings.rag_max_upload_bytes:
            return {"filename": name, "status": "REJECTED", "reason": "file exceeds the 50 MB limit"}
        try:
            detected = detect(name, data)
        except UnsupportedFile as exc:
            return {"filename": name, "status": "REJECTED", "reason": str(exc)}
        digest = sha256(data)
        sid = source_id or uuid.uuid4()
        key = svc.files.key(ws, sid, digest, detected.extension)
        doc = NewDocument(workspace_id=ws, file_name=name, title=meta.get("title") or name.rsplit(".", 1)[0],
                          mime=detected.mime, size_bytes=len(data), sha256=digest, storage_key=key,
                          project_id=meta.get("projectId"), project_name=meta.get("projectName"),
                          locality=meta.get("locality"), crm_document_id=meta.get("crmDocumentId"),
                          crm_file_id=meta.get("crmFileId"), doc_type=meta.get("docType"),
                          languages=meta.get("languages"), actor_id=actor_id, source_id=sid)
        svc.files.write(key, data)
        try:
            created = await svc.store.create_version(doc, settings.job_max_attempts,
                                                     existing_source=source_id is not None)
        except Duplicate as dup:
            svc.files.delete(key)
            existing = dup.existing
            return {"id": str(existing["source_id"]), "filename": name, "status": "DUPLICATE",
                    "duplicate": True, "reason": "this file has already been uploaded",
                    "existingStatus": existing["status"]}
        except (Conflict, LookupError) as exc:
            svc.files.delete(key)
            return {"filename": name, "status": "REJECTED", "reason": str(exc)}
        return {"id": str(created["source_id"]), "filename": name, "status": created["status"],
                "version": created["version"], "duplicate": False}

    def _meta(project_id: str | None, project_name: str | None, locality: str | None, crm_document_id: str | None,
              crm_file_id: str | None, title: str | None, doc_type: str | None, language: str | None) -> dict:
        meta: dict[str, Any] = {"projectName": project_name or None, "locality": locality or None,
                                "title": (title or "").strip()[:300] or None}
        for key, value in (("projectId", project_id), ("crmDocumentId", crm_document_id), ("crmFileId", crm_file_id)):
            meta[key] = _int_id(value, key) if value not in (None, "") else None
        if doc_type:
            if doc_type not in DOC_TYPES:
                raise HTTPException(422, f"unknown docType {doc_type}")
            meta["docType"] = doc_type
        if language:
            if language not in LANGS:
                raise HTTPException(422, f"unknown language {language}")
            meta["languages"] = [language]
        return meta

    async def upload(ws: int, request: Request, files: list[UploadFile] = File(...),
                     projectId: str | None = Form(None), projectName: str | None = Form(None),
                     locality: str | None = Form(None), crmDocumentId: str | None = Form(None),
                     crmFileId: str | None = Form(None), title: str | None = Form(None),
                     docType: str | None = Form(None), language: str | None = Form(None),
                     actor_id: int | None = Depends(actor)) -> JSONResponse:
        svc = svc_dep(request)
        if not files or len(files) > 20:
            raise HTTPException(422, "choose between 1 and 20 files per batch")
        meta = _meta(projectId, projectName, locality, crmDocumentId, crmFileId, title, docType, language)
        if meta.get("crmDocumentId") and len(files) != 1:
            raise HTTPException(422, "a CRM document has exactly one file")
        results = []
        for f in files:
            existing = None
            if meta.get("crmDocumentId"):
                existing = await svc.store.by_crm_document(ws, meta["crmDocumentId"])
            results.append(await _store_upload(svc, ws, f, source_id=existing["current"]["source_id"] if existing else None,
                                               meta=meta, actor_id=actor_id))
        return JSONResponse({"batchId": uuid.uuid4().hex, "results": results}, status_code=202)

    app.post("/v1/workspaces/{ws}/sources", dependencies=[Depends(crm)])(upload)
    app.post("/v1/workspaces/{ws}/batches", dependencies=[Depends(crm)])(upload)

    @app.get("/v1/workspaces/{ws}/sources", dependencies=[Depends(crm)])
    async def list_sources(ws: int, request: Request, page: int = 0, size: int = 20, search: str = "",
                           status: str = "", projectId: str | None = None) -> dict:
        if page < 0 or not 1 <= size <= 100:
            raise HTTPException(422, "invalid pagination")
        svc = svc_dep(request)
        project = _int_id(projectId, "projectId") if projectId else None
        result = await svc.store.list_sources(ws, page=page, size=size, search=search[:200],
                                              status=status[:30], project_id=project)
        return {**result, "items": [source_json(d, threshold=settings.low_confidence_threshold)
                                    for d in result["items"]]}

    def _source_id(value: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except ValueError:
            raise HTTPException(422, "source id must be a UUID") from None

    async def _source_response(svc: Services, ws: int, sid: uuid.UUID) -> dict:
        try:
            source = await svc.store.source(ws, sid)
        except LookupError:
            raise HTTPException(404, "source not found") from None
        return source_json(source["current"], source["pages"], settings.low_confidence_threshold,
                           source["versions"])

    @app.get("/v1/workspaces/{ws}/sources/{source_id}", dependencies=[Depends(crm)])
    async def source_detail(ws: int, source_id: str, request: Request) -> dict:
        return await _source_response(svc_dep(request), ws, _source_id(source_id))

    @app.post("/v1/workspaces/{ws}/sources/{source_id}/replace", dependencies=[Depends(crm)])
    async def replace(ws: int, source_id: str, request: Request, files: list[UploadFile] = File(...),
                      actor_id: int | None = Depends(actor)) -> JSONResponse:
        svc, sid = svc_dep(request), _source_id(source_id)
        if len(files) != 1:
            raise HTTPException(422, "choose exactly one replacement file")
        try:
            current = (await svc.store.source(ws, sid))["current"]
        except LookupError:
            raise HTTPException(404, "source not found") from None
        meta = {"projectId": current["project_id"], "projectName": current["project_name"],
                "locality": current["locality"], "crmDocumentId": current["crm_document_id"],
                "crmFileId": current["crm_file_id"], "title": current["title"],
                "docType": current["doc_type"] if current["doc_type_source"] == "crm" else None}
        result = await _store_upload(svc, ws, files[0], source_id=sid, meta=meta, actor_id=actor_id)
        return JSONResponse({"results": [result]}, status_code=202)

    @app.post("/v1/workspaces/{ws}/sources/{source_id}/retry", dependencies=[Depends(crm)])
    async def retry(ws: int, source_id: str, request: Request) -> JSONResponse:
        svc, sid = svc_dep(request), _source_id(source_id)
        try:
            await svc.store.retry(ws, sid)
        except LookupError:
            raise HTTPException(404, "source not found") from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        return JSONResponse(await _source_response(svc, ws, sid), status_code=202)

    @app.post("/v1/workspaces/{ws}/sources/{source_id}/unpublish", dependencies=[Depends(crm)])
    async def unpublish_source(ws: int, source_id: str, request: Request) -> dict:
        svc, sid = svc_dep(request), _source_id(source_id)
        try:
            await svc.store.unpublish(ws, sid)
        except LookupError:
            raise HTTPException(404, "source not found") from None
        return await _source_response(svc, ws, sid)

    @app.post("/v1/workspaces/{ws}/sources/{source_id}/publish", dependencies=[Depends(crm)])
    async def publish_source(ws: int, source_id: str, request: Request) -> dict:
        svc, sid = svc_dep(request), _source_id(source_id)
        try:
            await svc.store.republish(ws, sid)
        except LookupError:
            raise HTTPException(404, "source not found") from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        return await _source_response(svc, ws, sid)

    @app.delete("/v1/workspaces/{ws}/sources/{source_id}", dependencies=[Depends(crm)])
    async def delete_source(ws: int, source_id: str, request: Request) -> JSONResponse:
        svc, sid = svc_dep(request), _source_id(source_id)
        try:
            keys = await svc.store.delete(ws, sid)
        except LookupError:
            raise HTTPException(404, "source not found") from None
        for key in keys:
            await asyncio.to_thread(svc.files.delete, key)
        return JSONResponse({"id": str(sid), "status": "DELETED"}, status_code=202)

    # ---- the CRM's document contract (RestRagServiceClient)

    def _doc_ids(body: dict[str, Any]) -> tuple[int, int | None, int]:
        ws = _int_id(body.get("workspaceId"), "workspaceId")
        project = _int_id(body["projectId"], "projectId") if body.get("projectId") not in (None, "") else None
        doc = _int_id(body.get("documentId") or body.get("resourceId"), "documentId")
        return ws, project, doc

    async def _reindex(svc: Services, current: dict[str, Any]) -> None:
        data = svc.files.read(current["storage_key"])
        key = svc.files.key(current["workspace_id"], current["source_id"], current["sha256"],
                            "." + current["file_name"].rsplit(".", 1)[-1].lower())
        svc.files.write(key, data)
        await svc.store.create_version(NewDocument(
            workspace_id=current["workspace_id"], file_name=current["file_name"], title=current["title"],
            mime=current["mime"], size_bytes=current["size_bytes"], sha256=current["sha256"], storage_key=key,
            project_id=current["project_id"], project_name=current["project_name"], locality=current["locality"],
            crm_document_id=current["crm_document_id"], crm_file_id=current["crm_file_id"],
            doc_type=current["doc_type"] if current["doc_type_source"] == "crm" else None,
            source_id=current["source_id"]), settings.job_max_attempts, existing_source=True, reindex=True)

    @app.post("/v1/content/index", dependencies=[Depends(crm)])
    async def content_index(body: dict[str, Any], request: Request) -> dict:
        """Index a CRM document's editable text (documents that carry a file use /sources)."""
        svc = svc_dep(request)
        ws, project, crm_doc = _doc_ids(body)
        existing = await svc.store.by_crm_document(ws, crm_doc)
        content = str(body.get("content") or "").strip()
        if not content:
            if existing is None:
                raise HTTPException(422, "nothing to index: no content and no uploaded file")
            current = existing["current"]
            # Publishing a document whose file is already live (or still being processed) must not
            # parse it again: page parsing is the paid step. Only an unpublished file is brought
            # back, and only a failed one is re-parsed; /v1/documents/reindex always re-parses.
            if current["status"] in ("PUBLISHED", "UPLOADED", "PARSING", "EMBEDDING"):
                pass
            elif current["status"] == "UNPUBLISHED":
                try:
                    await svc.store.republish(ws, current["source_id"])
                except Conflict:
                    await _reindex(svc, current)
            else:
                await _reindex(svc, current)
        else:
            data = content.encode("utf-8")
            digest = sha256(data)
            current = existing["current"] if existing else None
            if current is not None and current["sha256"] == digest and current["status"] in (
                    "PUBLISHED", "UPLOADED", "PARSING", "EMBEDDING"):
                pass  # unchanged text that is already live or on its way
            else:
                sid = current["source_id"] if current else uuid.uuid4()
                key = svc.files.key(ws, sid, digest, ".md")
                svc.files.write(key, data)
                language = body.get("language") if body.get("language") in LANGS else None
                try:
                    await svc.store.create_version(NewDocument(
                        workspace_id=ws, file_name=f"crm-document-{crm_doc}.md",
                        title=str(body.get("title") or f"Document {crm_doc}")[:300], mime="text/markdown",
                        size_bytes=len(data), sha256=digest, storage_key=key, project_id=project,
                        project_name=body.get("projectName"), locality=body.get("projectLocation"),
                        crm_document_id=crm_doc, languages=[language] if language else None,
                        doc_type=body.get("docType") if body.get("docType") in DOC_TYPES else None,
                        source_id=sid), settings.job_max_attempts, existing_source=current is not None,
                        reindex=current is not None)
                except Duplicate as dup:
                    if dup.existing["crm_document_id"] != crm_doc:
                        raise HTTPException(409, "identical content is already indexed for another document") from None
        source = await svc.store.by_crm_document(ws, crm_doc)
        return status_json(source, ws, crm_doc, settings.low_confidence_threshold)

    @app.post("/v1/documents/reindex", dependencies=[Depends(crm)])
    async def reindex(body: dict[str, Any], request: Request) -> dict:
        svc = svc_dep(request)
        ws, _project, crm_doc = _doc_ids(body)
        existing = await svc.store.by_crm_document(ws, crm_doc)
        if existing is None:
            return await content_index(body, request)
        await _reindex(svc, existing["current"])
        source = await svc.store.by_crm_document(ws, crm_doc)
        return status_json(source, ws, crm_doc, settings.low_confidence_threshold)

    @app.post("/v1/documents/status", dependencies=[Depends(crm)])
    async def document_status(body: dict[str, Any], request: Request) -> dict:
        svc = svc_dep(request)
        ws, _project, crm_doc = _doc_ids(body)
        source = await svc.store.by_crm_document(ws, crm_doc)
        return status_json(source, ws, crm_doc, settings.low_confidence_threshold)

    @app.post("/v1/content/unpublish", dependencies=[Depends(crm)])
    async def content_unpublish(body: dict[str, Any], request: Request) -> dict:
        svc = svc_dep(request)
        ws, _project, crm_doc = _doc_ids(body)
        source = await svc.store.by_crm_document(ws, crm_doc)
        if source is None:
            return {"documentId": str(crm_doc), "workspaceId": str(ws), "status": "UNPUBLISHED"}
        await svc.store.unpublish(ws, source["current"]["source_id"])
        source = await svc.store.by_crm_document(ws, crm_doc)
        return status_json(source, ws, crm_doc, settings.low_confidence_threshold)

    return app


async def _build_reranker(settings: Settings, svc: Services) -> rerank_mod.Reranker | None:
    if settings.reranker == "none":
        return None
    if settings.provider_mode == "fake":
        return rerank_mod.OverlapReranker()
    if settings.reranker == "cohere":
        if not settings.cohere_api_key:
            log.error("RERANKER=cohere but COHERE_API_KEY is empty; reranking disabled")
            return None
        return rerank_mod.CohereReranker(settings.cohere_api_key, settings.cohere_rerank_model, svc.http)
    reranker = rerank_mod.BgeReranker(settings.reranker_model)
    try:
        await asyncio.to_thread(reranker.load)
        log.info("reranker %s loaded (%.1f ms/pair)", reranker.name, reranker.ms_per_pair)
        return reranker
    except Exception as exc:  # noqa: BLE001 - missing model/torch must not take retrieval down
        log.error("could not load %s (%r); reranking disabled", settings.reranker_model, exc)
        return None
