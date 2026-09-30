# EstraOS property knowledge ingestion

Implements `../../rag_plans/rag.md` plus `rag_property_type_amendment.md`.
This service ingests and indexes knowledge; it **does not change the voice agent or
implement its retrieval/ranking/conversation tools**.

## Flow

CRM Files → authenticated Java proxy → source/version + PostgreSQL queue →
native extraction / selective OCR → deterministic facts / selective Mistral →
per-source contributions → field-level canonical state → semantic sections →
local CPU embeddings → atomic canonical + FTS + vector publication.

The CRM database is unchanged. Map every existing CRM workspace ID to its own
**new** knowledge database, never to the operational CRM database. Database binding
is checked by the migration. IDs for existing users/workspaces remain numeric;
source/version/batch/job identifiers in this separate ingestion API are UUIDs.

All types use the same nullable-field canonical model: apartments, villas, shops,
showrooms, offices, warehouses, industrial assets, land and future types. Common
type/subtype/location/price/area/availability fields are standardized. Explicit
type-specific facts remain in `rag_entities.canonical` JSONB and shared search
sections; BHK/bedrooms/bathrooms/balconies are never required or invented.

## Run with Docker

1. Copy `.env.example` to `.env`. Set a unique DB password, a random service token
   (at least 24 characters), and the **actual existing CRM workspace ID** in
   `RAG_DATABASES_JSON`. URL-encode DSN passwords. The example `knowledge-db` hostname
   applies inside Compose; use localhost + mapped port for a native worker/API.
2. Run from this directory:

   ```powershell
   docker compose up --build -d
   docker compose logs -f worker
   ```

3. Set `RAG_INGESTION_URL=http://localhost:8090` and the same
   `RAG_INGESTION_TOKEN` in the CRM backend environment, then restart the backend.
   A containerized CRM uses `http://api:8090` on a shared network instead.
4. Files → Knowledge sources → Upload files. Selecting files uploads one batch;
   every file gets its own outcome and publication transaction. Legacy stored
   files stay available in a separate tab and are not silently migrated.

Default Compose exposes the new database only on `127.0.0.1:55432` and the API only
on `127.0.0.1:8090`. Change the mapping if Windows reserves a port. Named volumes
retain source files, model cache and the database. Do not use `down -v` to restart.
Initial model download requires internet; warm execution uses local CPU weights.
Do not point the database volume or DSN at the existing CRM data directory.

For more clients, provision another database on this server and append its DSN to
the JSON map. Each database is bound to exactly one CRM workspace. Re-run
`estraos-rag migrate` after adding a store. Migrations are idempotent; running
them twice does not reset source data. Keep application connections off while
upgrading a deployed schema.

## Native Python development

Python 3.12 recommended. PostgreSQL must have the real `vector` extension installed.

```powershell
uv venv .venv
uv pip install --python .venv/Scripts/python.exe torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/Scripts/python.exe -c constraints.txt -e '.[test]'
.venv/Scripts/estraos-rag.exe migrate
.venv/Scripts/estraos-rag.exe api
# Separate terminal, same .env and storage path:
.venv/Scripts/estraos-rag.exe worker
```

The CLI loads the current directory's `.env` without overriding existing variables.
Use native-host DSNs (not the Compose hostname). The API and worker must share the
same storage path and DSN map. Only the worker parses and embeds; API requests queue
durable work. `worker --once` processes at most one queued operation per store.
Local scanned-PDF OCR needs Tesseract plus eng/hin/mar/guj language packs; Docker
installs them. `RAG_OCR_LANGUAGES` defaults to `eng` for native installations.

## Models and extraction

The measured embedding selection is `intfloat/multilingual-e5-small`, immutable
revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions. See
[benchmark report](benchmarks/REPORT.md) for actual results and limitations.
No paid embedding API or fake/hash fallback is used. Exact vector search is the
baseline at approximately 1,000 properties; no ANN index is introduced.

CSV/XLS/XLSX and clearly labeled text use deterministic extraction. Native PDF and
DOCX text are retained with locators; scanned PDF pages and embedded PDF/DOCX
image parts use local OCR. Embedded-image text keeps its own page/block/image
locator; images with no readable text produce a warning, not inferred visual facts.
Documents requiring
narrative/layout interpretation need `MISTRAL_API_KEY` and an explicit
`MISTRAL_EXTRACTION_MODEL`. Missing configuration fails that job clearly while
leaving live knowledge intact. No external calls occur for deterministic inputs.
Mistral receives extracted document text when needed; do not configure it for
documents that must never leave the machine. No crawler, document-link following,
image persistence, macro execution or formula evaluation is implemented.

PDF, DOCX, XLS/XLSX, CSV, TXT and Markdown are accepted. DOC and ZIP are rejected
as knowledge sources; existing opaque ZIP files remain in legacy storage. Maximum
50 MB/file, 20 files/batch, 200 MB combined batch. Encrypted files are permanent
rejections: upload an unencrypted replacement, not Retry.

## Publication and recovery

- SHA-256 duplicate detection includes active/queued/processing versions, not only
  filenames. One pending operation per stable source; one logical job per database
  is serialized by a session advisory lock, including across worker processes.
- Failed jobs are not automatically retried. Files UI Retry reuses the stored file.
  Interrupted PROCESSING work becomes FAILED when a new worker obtains the lock.
- Successful newer sources win only conflicting fields. Non-conflicting old facts
  remain, with per-fact provenance. Strong explicit identity matches may merge;
  name/BHK/area alone never cross-source merge uncertain listings.
- Replace keeps the old version live through parsing, reconciliation and embedding.
  One transaction switches canonical, FTS and vector state only after all succeed.
- Delete first reconstructs remaining contributions and embeds affected sections,
  then publishes atomically. Physical files/raw extraction are cleaned afterward.
  Filesystem cleanup failures stay in `rag_file_cleanup` for separate cleanup retry;
  they do not roll back or rerun ingestion. Audit/version metadata is retained.
- Ambiguous newer numeric values clear stale typed filters, retain their original
  wording/provenance in canonical unresolved facts, and become source-qualification
  search sections. Explicit price ranges produce both min/max bounds.

Changing embedding model/dimension requires full re-embedding, never mixed models:

```powershell
.venv/Scripts/estraos-rag.exe reembed --workspace 1 --actor 7 --model intfloat/multilingual-e5-small --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
```

Use an existing CRM actor ID. A failed re-embedding leaves the previous set live;
rerun the command manually to retry. After success, update worker model configuration
to match before restarting it. The read view `rag_live_knowledge` exposes only the
active embedding set and its complete model identity. Voice queries must use the
same pinned provider with `embed_queries` (`query: ` prefix), while documents use
`passage: `. Read-side exact filters and FTS are available; voice integration remains
a separate task by specification.

## Verification

```powershell
# Existing dedicated/disposable pgvector test DB; never use the CRM DB.
$env:RAG_TEST_DATABASE_URL='postgresql://test_user:test_password@127.0.0.1:15433/rag_verify?connect_timeout=5'
.venv/Scripts/python.exe -m pytest tests -q

$env:RAG_BENCHMARK_DATABASE_URL=$env:RAG_TEST_DATABASE_URL
.venv/Scripts/python.exe benchmarks/benchmark_embeddings.py --model e5
.venv/Scripts/python.exe benchmarks/benchmark_embeddings.py --model minilm
```

Lifecycle tests create/drop uniquely named private schemas, not databases. Without
the test DSN they are explicitly skipped; passing only unit tests is not database
verification. Embedding failure tests inject a test-only provider; the benchmark
uses actual downloaded models. Benchmark corpus and `examples/mixed-property-types.csv`
are **synthetic fixtures, not real listings**.

For the CRM checks, run `npm test`, `npm run build`, and `npm run lint` in
`../frontend`. Run `mvn -Dspring.flyway.enabled=true test` in `../backend`:
its disposable Testcontainers database needs migrations enabled, while the existing
application configuration intentionally leaves Flyway disabled. Do not enable
migrations against an existing operational database just to run these tests.

To exercise the real OCR tests and database lifecycle from the built Docker image:

```powershell
docker build -t estraos-rag:local .
docker run --rm --entrypoint python `
  -e RAG_TEST_DATABASE_URL='postgresql://test_user:test_password@host.docker.internal:15433/rag_verify?connect_timeout=5' `
  --mount "type=bind,source=$($PWD.Path)/tests,target=/app/tests,readonly" `
  --mount "type=bind,source=$($PWD.Path)/examples,target=/app/examples,readonly" `
  estraos-rag:local -m pytest tests -q -p no:cacheprovider
```

Real OCR tests explicitly skip on native systems without Tesseract; Docker includes
it. Tests use isolated schemas and synthetic content, not existing client documents.
See [implementation ledger](IMPLEMENTATION.md) for the recorded verification and
the distinction between tested implementation and production configuration.

## Known limits

- Lexical evidence and conservative negation checks reduce unsupported extraction,
  but do not prove arbitrary semantic entailment. OCR and LLM extraction can still
  misread a document; evaluate representative client documents before production.
- No automatic translations/aliases or broad inferred property traits are generated.
- Interpretation currently rejects documents beyond its 240,000-character input
  budget rather than silently truncating them. Embedding sections exceeding the
  pinned model's token limit fail publication rather than lose facts silently.
- The multilingual benchmark is a small synthetic diagnostic, not a production
  accuracy guarantee. The property-type amendment has parser/index regression
  coverage; it does not imply measured multilingual retrieval quality for every type.
- Development dependency deprecation warnings from Starlette/httpx remain visible
  in tests. No production secrets or storage paths are returned in source history.
