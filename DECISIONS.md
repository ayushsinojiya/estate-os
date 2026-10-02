# Decisions

One line per decision taken while building the RAG service, the voice agent and the CRM additions,
with the reason. Newest at the bottom of each section.

## Setup

- Java 21 is at `/opt/homebrew/opt/openjdk@21` but not on the default PATH; every Maven run sets `JAVA_HOME` to it rather than changing the machine's Java setup.
- `backend/src/main/resources/application.yml` was entirely commented out and `application.properties` is gitignored, so a fresh clone could not start or test the CRM; the YAML is restored as committed, env-driven config (same keys/defaults as `application.properties.example`), and a local `application.properties` still overrides it.
- Baseline before any change: backend `mvn test` 46/46 passing (with the restored config).

## Phase 1 — voice engine

- `last try/` does not exist in the repository; nothing to delete. README and `deploy/azure/deploy.sh` now point at `/voice-agent`.
- The bank agent has no tool-calling loop, outbound dialer, call registry, retry outbox or metrics module; they were written new in `/voice-agent` (labelled NEW in `voice-agent/docs/ENGINE_INVENTORY.md`), keeping the bank's code style.
- The bank's language helpers lived in `app/domain/`; they moved to `app/lang/` so `app/domain/` holds only the domain seam. Imports were the only change.
- Gujarati was added to language detection, Sarvam STT/TTS language codes and spoken-form tables; en/hi/mr behaviour and every tuned speech setting are unchanged.
- Banking words (account, loan, EMI, …) were removed from the Devanagari transliteration table and are now left to the TTS, so no banking vocabulary remains in `app/`.
- The banking-vocabulary scan allowlists exactly one module, `app/domain/real_estate/sensitive.py`, because refusing Aadhaar/PAN/OTP/financing questions requires naming them.
- The engine's single-letter-prefix reading quirk (`P52…` → "पीपाँच…") is existing bank behaviour and was not retuned.
- The tool loop runs at most `MAX_TOOL_HOPS=3` model calls with tools, then one without, so a model that keeps calling tools still answers.
- Whole earlier turns (including tool calls and results) are replayed to the model (`HISTORY_TURNS=4`) instead of the bank's last 6 text messages, so a slot list fetched one turn earlier is still available when the caller picks one.
- Domain HTTP routes are registered from the composition root (`app/wiring.py`), the only engine module that names the domain.

## Phase 2 — knowledge service (RAG)

- One knowledge database for every workspace (`RAG_DATABASE_URL`), replacing the old per-workspace `RAG_DATABASES_JSON`; isolation is a `workspace_id` filter in every statement, tested at every layer.
- Driver: psycopg 3 (async) with a pool; pgvector types registered per connection; `hnsw.iterative_scan=relaxed_order` set when the server supports it so filtered HNSW scans still return k rows.
- Each upload version is a `kb_documents` row; `source_id` (UUID) is the stable identity the CRM addresses. Superseded versions get status `SUPERSEDED` (added to the requested status list) rather than `UNPUBLISHED`, so "the user withdrew it" and "a newer version replaced it" stay distinguishable.
- Chunk status is denormalised onto `kb_chunks` (`PENDING`/`PUBLISHED`/`UNPUBLISHED`) and changed in the same transaction as the document, so retrieval filters one table.
- The duplicate check runs on upload (same bytes live in the workspace → `DUPLICATE`); the unique index only guards *published* bytes, so an explicit reindex of a file can be processed while its old version is still live.
- Parallel vector/keyword/name searches share one exported snapshot (`pg_export_snapshot` + `SET TRANSACTION SNAPSHOT`). Found by the atomic-swap test: without it a query could straddle a publish and return both versions.
- A project scope also returns workspace-wide documents (`project_id IS NULL`), because a builder's general FAQ applies to every project.
- A third retrieval signal, trigram `word_similarity` on the context header, is fused with vector and keyword lists; it catches loosely spelled project names and RERA numbers.
- Token counts are estimated from UTF-8 length (≈4 bytes/token) instead of tiktoken, which downloads its vocabulary at runtime and cannot run in a sealed container or offline tests.
- PPTX is parsed with python-pptx (titles, text frames, tables) rather than rendered for the vision model; rendering needs LibreOffice (~400 MB) in the image. Slides are marked confidence 0.9.
- DOCX is parsed with python-docx (headings, lists, tables). It is not in the vision list in the brief and has no fixed pages.
- A page whose vision parse fails after retries falls back to the PDF text layer at confidence 0.5 (flagged), so one bad page never fails a brochure.
- The voice path returns query-focused snippets (best-matching sentences/table rows within 900 chars, table header kept) instead of a head-truncated chunk; head truncation lost answers in packed sections (eval recall 0.867 → 0.967).
- Reranking predicts its own latency from measured per-pair cost and is skipped when the prediction exceeds `RERANK_BUDGET_MS`; a call that overruns is also cut off at the budget.
- The bge reranker needs torch; the image installs CPU-only torch and the model downloads to a volume on first start. If loading fails, retrieval continues without reranking and `/healthz` says so.
- `PROVIDER_MODE=fake` exists so tests and offline evals run without keys: hashing embedder (lexical), PDF text layer, overlap reranker, no rewrite.
- **CRM status sync: the CRM polls** (`KnowledgeStatusSync`, every 30 s, plus on-demand from `processing-status`). The knowledge service holds no CRM credential.
- CRM documents now accept the formats the knowledge service ingests (PDF, DOCX, PPTX, XLSX, XLS, CSV, TXT, MD, JPG, PNG, WEBP) with magic-byte checks, up to 50 MB. The uploaded file is the source of truth: publishing a file-backed document re-indexes the file, not the editable text.
- Files-page uploads in a supported format are also sent as workspace-wide knowledge (`managed_files.knowledge_*`, migration V5); deleting the file deletes the source.
- The RAG client is REST whenever `RAG_SERVICE_URL` is set, even with `INTEGRATIONS_MODE=mock`; voice and notifications still follow the mode. `RagIngestionService` uses the same URL and `RAG_SERVICE_TOKEN` (old `RAG_INGESTION_*` settings removed).
- The mock RAG client simulates automatic publication (upload → UPLOADED; next status check → PUBLISHED) so the demo shows the lifecycle; it still returns no search results rather than inventing brochure text.
- `database/migrations` was missing V4; it is mirrored now along with V5.
- No OpenAI key was available on the build machine, so evals ran with `PROVIDER_MODE=fake`; the numbers in `rag/README.md` say so.
