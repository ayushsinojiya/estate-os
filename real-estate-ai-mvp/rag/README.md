# EstraOS knowledge service (RAG)

Ingests a builder's documents (brochures, price sheets, payment plans, FAQs, RERA and legal
papers, floor plans) and answers retrieval requests from two callers: the voice agent during a live
call, and the CRM for recommendations and source management. Python 3.12, FastAPI, PostgreSQL with
pgvector. One image, three roles:

```bash
python -m rag_service migrate   # forward-only schema migrations
python -m rag_service api       # HTTP API on :8090
python -m rag_service worker    # ingestion worker (run as many as you like)
```

## What it does

```
upload ─► UPLOADED ─► PARSING ─► EMBEDDING ─► PUBLISHED      (FAILED, UNPUBLISHED, SUPERSEDED, DELETED)
            │            │           │
            │            │           └─ OpenAI embeddings in batches of 256, model recorded per chunk
            │            └─ vision model per page (PDF/PPTX/images); pandas/openpyxl for sheets;
            │               python-docx for Word; classify doc type + language; structure-aware chunks
            └─ SHA-256 duplicate check per workspace; bytes stored on RAG_STORAGE_PATH
```

- **Storage.** One knowledge database (separate from the CRM's) with `workspace_id` on every row:
  `kb_documents` (one row per version; `source_id` is the stable identity), `kb_pages` (parsed
  Markdown per page with provider, confidence and page-image hash), `kb_chunks` (content, context
  header, `vector(N)` embedding, `simple` tsvector, status), `kb_jobs` (durable queue claimed with
  `FOR UPDATE SKIP LOCKED`, exponential backoff). Indexes: HNSW (cosine) on the embedding, GIN on the
  tsvector, B-tree on `(workspace_id, project_id, status)`, `pg_trgm` on titles and context headers.
  Text search uses the `simple` configuration: Postgres has no stemmers for Hindi, Marathi or
  Gujarati, and pretending otherwise would mangle them.
- **Parsing.** PDF pages and images are rendered and transcribed to faithful Markdown by a vision
  model (`PARSER_PROVIDER=openai` with `gpt-4o-mini`, or `mistral` OCR), a few pages at a time with
  retries. The prompt keeps Devanagari and Gujarati in their script and asks for a self-reported
  confidence. A page that still fails falls back to the PDF's own text layer and is flagged.
  Spreadsheets and CSVs never go to a model; each sheet becomes a table. Slides are read with
  python-pptx (LibreOffice is not in the image; see DECISIONS.md).
- **Chunking** follows structure: headings split sections, small neighbouring sections are packed
  (≈250–450 tokens), long sections split with ≈15% overlap inside themselves only. Tables are never
  cut through a row and always repeat their header; tables with more than six rows also get one
  `TABLE_ROW` chunk per row (`Charge: Floor rise; Amount: ₹40 per sq ft per floor`). Every FAQ
  question with its answer is exactly one chunk. Each chunk is embedded together with a context
  header: `Project: Sahyadri Grove (Baner, Pune) · Brochure · Section: Amenities > Clubhouse · Page 4`.
- **Publishing** is automatic once every chunk is embedded. A new version (replace or reindex)
  goes live in one transaction that also removes the old version's chunks, so retrieval sees the
  old version or the new one, never both and never neither. Unpublish and delete take chunks out of
  retrieval in the same transaction. Pages parsed with low confidence are published but listed in
  `lowConfidencePages` and `warnings` so the UI can badge them.
- **Retrieval** embeds the query (LRU-cached), runs vector top-30, keyword (`ts_rank_cd`) top-30
  and a trigram name match in parallel from one shared database snapshot, fuses them with
  Reciprocal Rank Fusion (k=60), and reranks the top 20 when it fits the budget
  (`RERANKER=bge|cohere|none`; local `BAAI/bge-reranker-v2-m3` by default). Reranking predicts its
  own latency from what it has measured and is skipped, with a log line, when the prediction exceeds
  `RERANK_BUDGET_MS` (150). On the live-call path the query embedding (a provider round-trip,
  400–900 ms measured from Pune) has its own budget, `VOICE_EMBED_BUDGET_MS` (300): past it the
  answer comes from the keyword and name searches alone (`"vector": "skipped:budget"` in the
  response) and the late embedding is still cached for the next time that question is asked.
- **Live inventory is never embedded.** Unit prices, availability and BHK counts come only from the
  CRM. Price-sheet chunks are for structure (payment stages, floor rise, PLC, parking, maintenance,
  GST). Every retrieval response carries `"inventoryAuthoritative": "crm"`.

## API

| Endpoint | Caller | Purpose |
| --- | --- | --- |
| `POST /v1/voice/retrieve` | voice agent (`RAG_VOICE_TOKEN`, one workspace) or CRM | Hot path. `{workspaceId, projectId?, query, docTypes?, language?, k=4}` → chunks with `documentId`, `title`, `docType`, `page`, `sectionPath`, `score`, short query-focused `content`. No answer generation. |
| `POST /v1/knowledge/search` | CRM | `RestRagServiceClient` contract: `{results:[{workspaceId,projectId,documentId,status:"PUBLISHED",language,text,pageReference,score}]}`, honouring `publishedDocumentIds`. Rewrites Hinglish/Marathi/Gujarati to an English query plus two paraphrases first. |
| `POST /v1/workspaces/{ws}/sources` (alias `/batches`) | CRM | Multipart upload (`files`, optional `projectId`, `projectName`, `locality`, `crmDocumentId`, `crmFileId`, `title`, `docType`, `language`). 202 with per-file `UPLOADED`/`DUPLICATE`/`REJECTED`. |
| `GET /v1/workspaces/{ws}/sources`, `GET …/sources/{id}` | CRM | List (`{items,total,page,size}`) and detail (versions, pages, low-confidence pages, cost). |
| `POST …/sources/{id}/replace`, `/retry`, `/unpublish`, `/publish`; `DELETE …/sources/{id}` | CRM | Version, retry a failed ingest, withdraw, restore, delete. |
| `POST /v1/content/index`, `/v1/documents/reindex`, `/v1/documents/status`, `/v1/content/unpublish` | CRM | The CRM's document contract, keyed by its own `documentId`. |
| `GET /healthz` | anyone | Database, provider mode, embedding model, parser, reranker, queue depth. |

**CRM status: the CRM polls.** It calls `/v1/documents/status` from the document's
processing-status endpoint and from a scheduled sync, and flips `property_documents.status` to
`PUBLISHED` when this service reports it. Polling keeps the knowledge service free of any
credential for the CRM; the cost is a delay of at most one sync interval.

## Configuration

See `.env.example`. The important ones: `RAG_DATABASE_URL`, `RAG_SERVICE_TOKEN`, `RAG_VOICE_TOKEN`
+ `RAG_VOICE_WORKSPACE_ID`, `OPENAI_API_KEY`, `PARSER_PROVIDER`, `EMBEDDING_MODEL`/`EMBEDDING_DIM`,
`RERANKER`, `REWRITE_ON_VOICE` (default false: the voice LLM writes English keyword queries itself).

`EMBEDDING_DIM` above 2000 stores `halfvec` (HNSW's limit for `vector` is 2000). With
`text-embedding-3-large` either keep 1536/1024 (the service requests that many dimensions) or set
3072 and get `halfvec`. The index remembers the model and dimension it was built with and the
service refuses to start against a different one, because mixing models silently ruins similarity.

Create the database once (the extensions need a superuser):

```sql
CREATE DATABASE estraos_knowledge;
\c estraos_knowledge
CREATE EXTENSION vector;
CREATE EXTENSION pg_trgm;
```

`PROVIDER_MODE=fake` runs entirely offline: a deterministic hashing embedder (lexical, not
semantic), the PDF text layer instead of vision, an overlap reranker, no query rewriting.

## Tests

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # needs Docker: Testcontainers starts pgvector/pgvector:pg17
```

Covered: workspace isolation at every layer, unpublished/deleted/in-progress documents never
returned, tables never split, XLSX row chunks, duplicate SHA, atomic version swap under concurrent
reads, voice-token workspace binding, the CRM document contract and allowlist, SKIP LOCKED claiming,
retry/backoff, RRF fusion, the rerank skip-on-budget and timeout paths, and `/v1/voice/retrieve`
latency with mocked providers.

## Measured results

**Latency** (`tests/test_latency.py`, 470 published chunks, embedding call simulated at 120 ms and
rerank at 60 ms, 60 sequential requests, Testcontainers Postgres on a laptop): **p50 196 ms,
p95 198 ms** server-side. Database search plus fusion is ≈18 ms of that; the target is p95 < 450 ms.

**Retrieval eval** (`python -m evals.run_eval`; 30 questions, 10 en / 7 hi / 7 mr / 6 gu, over a
synthetic brochure, XLSX price sheet and FAQ for a fictional project). Run offline
(`PROVIDER_MODE=fake`: hashing embedder, no reranker, no rewrite model) because no OpenAI key was
available on the build machine:

| Path | recall@4 | MRR |
| --- | --- | --- |
| voice (`/v1/voice/retrieve`, English keyword query as the voice LLM writes it) | **0.967** | **0.928** |
| CRM (`/v1/knowledge/search`, the caller's own words, no rewrite offline) | 0.600 | 0.542 |

Per language, voice: en 1.000 / 0.883, hi 0.857 / 0.857, mr 1.000 / 1.000, gu 1.000 / 1.000.
CRM: en 1.000 / 0.950, hi 0.571 / 0.464, mr 0.429 / 0.357, gu 0.167 / 0.167.

How to read this: the offline embedder only matches shared words, so a Marathi or Gujarati question
cannot match English text without the rewrite step, which needs a model. That is what the CRM-path
numbers show, not a property of the pipeline. Re-run with `OPENAI_API_KEY` set (live embeddings,
`gpt-4o-mini` rewriting, bge reranker) before relying on the multilingual numbers; results are
written to `evals/results/latest.json`.
