# rag.md implementation ledger

Authority: `D:/my hope/rag_plans/rag.md` (V1 ingestion only) and
`D:/my hope/rag_plans/rag_property_type_amendment.md`.

## Property-type amendment

Keep one generic PROJECT / CONFIGURATION / PROPERTY architecture. All residential
fields are nullable/optional; non-residential and future types retain explicit
type-specific fields in canonical JSONB and shared canonical search sections.
Added standardized subtype and availability metadata without category-specific tables.
Regression cases cover residential, shops, showrooms, offices, warehouses, industrial,
land and an unknown future type without requiring BHK or bedrooms.

## Gap analysis

The CRM has authenticated workspace users, a 50 MB filesystem upload endpoint, SHA-256 checks, and storage history. It has no source versions, durable ingestion jobs, canonical contributions, or pgvector ingestion. Existing RAG adapters are provisional retrieval adapters and are not this ingestion system. ZIP is accepted as an opaque stored file; no archive extraction exists. The voice source folder referenced by older documentation is not present in this checkout (only an archive remains).

## Decisions

- Separate Python service and polling worker; one configured PostgreSQL DSN per workspace/client. No CRM schema redesign. CRM proxies authenticated source actions and supplies existing user IDs.
- PostgreSQL session advisory lock serializes all logical jobs per client. Jobs committed before work; interrupted PROCESSING jobs become FAILED when the next worker acquires the lock, requiring manual Retry.
- Per-source contributions and provenance produce canonical entities and property-aware sections. Stage in memory/durable extracted versions, publish all affected canonical/keyword/vector rows in one transaction. Old rows remain readable until commit.
- Explicitly reject ZIP/DOC as knowledge sources in V1; retain original legacy file storage separately. This simplifies existing opaque ZIP support without inventing archive semantics. PDF, XLS/XLSX, CSV, DOCX, TXT/MD supported.
- Model selection requires real multilingual benchmark. Production embedding configuration must be explicit and carries immutable model metadata; no synthetic vector fallback.
- No Git repository exists in this workspace. Preserve existing files and use an on-disk ledger rather than creating unrelated Git state.

## Implemented

- Native CSV/XLS/XLSX/DOCX/PDF/text parsing, selective local OCR for scanned pages
  and embedded images, provenance and warning retention, optional grounded Mistral
  interpretation. No crawling or extracted-image persistence.
- Canonical PROJECT / CONFIGURATION / PROPERTY hierarchy, conservative identity,
  typed optional filters, dynamic facts, field-level source reconciliation,
  inherited search context distinguished from direct facts, semantic sections.
- SHA-256 duplicates, batch outcomes, durable PostgreSQL jobs, manual Retry,
  atomic replace/delete/re-embedding, post-publication cleanup and retained audit.
- Authenticated Java CRM bridge and Files knowledge-source UI, one upload action,
  source versions/stages/history, replace/retry/delete, separate legacy files tab.
- Real CPU embedding provider, benchmarked E5 and MiniLM, measured exact pgvector
  search, selected pinned E5 model. No fake-vector production fallback or ANN index.
- Local configuration, constraints-pinned dependencies, Docker image and Compose.

## Verification recorded on 2026-09-23

- Isolated PostgreSQL 16.15 / pgvector 0.8.6 in Docker; separate demo CRM database.
  Existing operational CRM data and schema were not migrated or modified.
- Real CRM upload through the Java proxy queued the synthetic mixed-property CSV;
  a worker using actual E5 weights published 5 properties / 19 sections / 384-D
  vectors. Re-running schema migration preserved all 19 live sections.
- Final built Docker image: 82 tests passed, zero skips, including real Tesseract
  PDF/DOCX OCR and real pgvector lifecycle tests. Native Windows: 80 passed, with
  the two real OCR tests explicitly skipped because native Tesseract is absent.
  Docker build, CLI startup/help, Compose configuration and installed OCR languages
  (English, Hindi, Marathi and Gujarati) verified.
- CRM backend: 46 tests, zero failures/errors/skips, with
  `mvn -q -Dspring.flyway.enabled=true test`. Bare Maven initially failed because
  the existing default disables migrations on its fresh test database; the override
  applies only to the test run and does not change the application's default.
- Frontend: 28 tests passed; production build and ESLint passed.
- Independent lifecycle review identified two identity defects; both were fixed
  with failing-then-passing regressions: replacement reusing an AI key no longer
  inherits facts belonging to another property, and location-based identity includes
  city/state/country. Reviewer independently rechecked both reproductions and 12
  geographic matching checks. Retry/start/replacement/retirement audit events are
  also covered by the database lifecycle regression.
- Actual browser: Files active version, processing logs and audit history verified.
  Measured 320, 768, 1024 and 1440 CSS-pixel widths: no root/body horizontal overflow;
  mobile table overflow stays inside the table container. Temporary viewport reset.
- Embedding benchmark: 1,000 synthetic properties / 2,016 sections / 40 multilingual
  queries. E5 recall@5 97.5%, warm query embedding median 24.92 ms; exact PostgreSQL
  query median 2.42 ms. These are separate diagnostic timings, not voice latency
  or a production accuracy guarantee. See `benchmarks/REPORT.md` and raw JSON.

## Deployment boundary and remaining validation

- No production credentials or live client database mapping were configured.
  Follow README and `.env.example` to provision dedicated knowledge databases and
  configure the same service token in the CRM and ingestion service.
- Live Mistral extraction was not invoked: no client API key/model was supplied.
  Deterministic ingestion, real OCR, real embeddings and publication were exercised;
  grounded interpreter behavior is covered using controlled responses. Validate
  representative client brochures before relying on extraction quality.
- Voice-agent retrieval/ranking/CRM actions are deliberately unchanged, as required
  by the V1 boundary. This delivers its knowledge store, not voice tool integration.
- The preview uses disposable synthetic/demo data, not the user's operational CRM.
  No actual customer documents were sent to an external extraction service.
- Third-party Starlette/httpx deprecations and Mockito dynamic-agent warnings remain.
  No database test is silently counted as passing when its dependency is absent.
