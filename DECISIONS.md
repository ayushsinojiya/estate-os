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
- Workspace-wide knowledge is uploaded on the Files page's *Knowledge sources* tab, which already goes through the `/api/v1/knowledge/*` proxy to the new service; that tab now reads the new contract (statuses, versions, page confidence). The *legacy stored files* tab is general storage and is deliberately **not** forwarded: agreements or ID copies kept there must never become retrievable by the voice agent. (A forwarding migration written earlier on this branch was removed before release; V5+ were renumbered.)
- The RAG client is REST whenever `RAG_SERVICE_URL` is set, even with `INTEGRATIONS_MODE=mock`; voice and notifications still follow the mode. `RagIngestionService` uses the same URL and `RAG_SERVICE_TOKEN` (old `RAG_INGESTION_*` settings removed).
- The mock RAG client simulates automatic publication (upload → UPLOADED; next status check → PUBLISHED) so the demo shows the lifecycle; it still returns no search results rather than inventing brochure text.
- `database/migrations` was missing V4; it is mirrored now along with V5.
- No OpenAI key was available on the build machine, so evals ran with `PROVIDER_MODE=fake`; the numbers in `rag/README.md` say so.

## Phase 3 — CRM additions

- Migrations V5 (visit slots, blackouts, project agents, `workspace_members.agent_available`, `users.phone`), V6 (callbacks, DNC), V7 (scheduled calls), V8 (WhatsApp provider-message indexes); mirrored in `database/migrations`. Every table has a `data jsonb` column so the existing `TenantRepository` helpers apply.
- Slots are computed per request from templates − blackouts − active appointments; nothing is materialised. Fallback order: project template → workspace default (project_id NULL) → built-in Mon–Sun 10:00–19:00, 60 min, capacity 3. Slots start at least `VISIT_MIN_LEAD_MINUTES` (60) from now.
- Round-robin uses `project_agents.last_assigned_at`; a project with no assigned agents rotates across all available workspace agents by their last automatic assignment.
- When no agent is free, the visit is still booked with the least-loaded agent as REQUESTED + `needsManagerReview`, and managers are notified. For that flagged booking only, the agent-overlap part of the existing overlap check is relaxed (the lead-overlap check still applies); without that, "book with the least-loaded agent" could never succeed when everyone is busy.
- Voice bookings go through `EstateService.saveVisit` (the existing visit logic, refactored to take options) so validation, history, notifications and reminders are shared with the UI path. UI-created visits keep their old behaviour (status set unconditionally); only voice-originated changes use the forward-only rule.
- Forward-only lead status: NEW < CONTACTED < QUALIFIED < VISIT_PLANNED < VISIT_COMPLETED < HANDED_OVER. NOT_INTERESTED/LOST rank lowest, so a positive action (booking a visit) brings such a lead forward; ingest never revives them. Ingest proposes QUALIFIED for WARM/HOT calls and CONTACTED otherwise (old records without a temperature behave exactly as before).
- An auto-handover (HOT or escalated) is created PENDING without moving the lead to HANDED_OVER, and there is at most one open handover per lead; later calls append their unanswered questions to it.
- Outbound scheduling lives in `scheduled_calls` with a unique idempotency key per purpose (`visit-<id>-day-before-<epoch>`, `callback-<id>-<epoch>`, `new-lead-<id>`, `reengage-<id>-<n>`); the key is also the agent request id, so the agent can deduplicate a retried dial.
- The dispatcher dials inside the claiming transaction (FOR UPDATE SKIP LOCKED), like `NotificationReminderService`; a crash after the agent accepted but before commit is covered by the agent's request-id deduplication.
- Daily attempt cap counts outbound sessions by their recorded `dialedAt` in the IST day, so manual and scheduled calls count the same way (found by the cap test: counting by `created_at` broke when the dispatcher's notion of "now" differed).
- A day-before reminder whose time has already passed is not created; a reminder that calling hours would push to within 30 minutes of the visit is skipped rather than placed too late.
- Manual "call now" in the CRM is not blocked by calling hours (the agent refuses outside them and the refusal is recorded); the scheduler defers instead. DNC is refused by both with 409.
- New leads are "web/portal" when their source contains WEB or PORTAL (or a known portal name); they get an OUTBOUND_NEW_LEAD call `NEW_LEAD_CALL_DELAY_S` after creation.
- The CRM's manual call sends `callType` OUTBOUND_NEW_LEAD for a NEW lead and CALLBACK otherwise, so the agent opens appropriately.
- `CallIngest` additionally carries `whatsappRequests` (BROCHURE, VISIT_CONFIRMATION) and `promptVersion`; the brief's `send_whatsapp(kind)` needs the requested kind to reach the CRM. Both are validated enums/lengths; unknown fields are still rejected.
- WhatsApp: mock in mock mode; in REST mode the Cloud API client when `WHATSAPP_PHONE_NUMBER_ID` and token are set, otherwise a client that records sends as failed. WhatsApp is optional, so a missing configuration must not stop the CRM from starting (unlike the other adapters).
- WhatsApp sends require `whatsappConsent=true` recorded from a call (with `whatsappConsentAt` and the call id); one send per purpose (`marker`), so an ingest resend never messages twice. The webhook verifies `X-Hub-Signature-256` with `WHATSAPP_APP_SECRET` and is the only unauthenticated API path added.
- Agent phone numbers for templates live on `users.phone`; seeded agents have demo numbers. `WHATSAPP_OFFICE_PHONE` fills in when an agent has none.
- `DemoSeed` runs before `ServiceAccountProvisioner` (`@Order`), so on a fresh database the demo workspace is workspace 1 and the voice agent's service account joins it. Demo knowledge (brochure, FAQ, charges sheet for two projects) is seeded as `PENDING_INDEX` and sent by the knowledge sync once the RAG service answers.
- CORS now also allows PATCH and DELETE (DELETE was already used by the Files page but missing from the allowed methods).
- Frontend tests failed on Node 26 because Node's own (empty) `localStorage` global shadows jsdom's; the test setup restores jsdom's storage, so `npm test` works on Node 20 through 26.
- Local stack: `compose.local.yaml` adds a pgvector PostgreSQL container (both databases) and `scripts/local_env.py` writes the git-ignored root `.env` from the provider keys file, generating the internal secrets once. A configured integration URL now selects the real client even when `INTEGRATIONS_MODE=mock`, so the local CRM talks to the real knowledge service and voice agent while notifications stay mocked.
- Live-call retrieval has an embedding budget (`VOICE_EMBED_BUDGET_MS`, 300): measured query-embedding latency to OpenAI from Pune was 450–900 ms against the agent's 600 ms lookup budget, so every knowledge question timed out. Past the budget the answer comes from keyword and name search (a few ms) and the late embedding is cached. CRM search keeps waiting for the embedding.
- The CRM integration HTTP client is pinned to HTTP/1.1: the JDK default (HTTP/2) sends an `h2c` upgrade on plain http, which uvicorn rejects, so every CRM → knowledge-service and CRM → voice-agent request failed with "rejected the request" (found on the first local deployment; the mock-server tests did not catch it).
- File management (swap, delete, publish, unpublish) acts on the knowledge source; when that source belongs to a project document (`crmDocumentId`), the CRM now keeps the document in step: a swap stores the new file on the document (so WhatsApp sends the current brochure) and lets the status sync follow it to PUBLISHED; a delete removes the stored file and returns the document to DRAFT with processingStatus DELETED, so it can neither be sent nor answered from. The knowledge service has already acted when this runs, so a failure here is logged rather than failing the request. Verified live: a swapped charges sheet answered with the new floor rise within one indexing pass (the old version served until then), and a deleted brochure returned no chunks and stayed deleted across sync cycles.
