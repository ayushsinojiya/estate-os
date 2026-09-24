# RAG Ingestion & Property Knowledge Architecture — V1

## 1. Purpose

This document is the implementation specification for the V1 real-estate RAG ingestion and property-knowledge system.

The system's responsibility is to ingest uploaded real-estate files, extract grounded property facts, reconcile those facts into a canonical latest state, generate searchable canonical representations, create embeddings, and publish a reliable PostgreSQL + pgvector knowledge store.

The voice agent will own retrieval, ranking/reranking, recommendation behavior, conversation behavior, and CRM actions. This RAG system is primarily responsible for data ingestion, canonicalization, indexing, provenance, lifecycle management, and safe publishing.

Primary priorities:

1. Maximum factual/data accuracy.
2. Latest successfully published property information must be the live state.
3. Never invent property facts.
4. Keep the voice-agent retrieval/read path simple.
5. Keep V1 operating cost near zero where practical.
6. Keep V1 simple enough to operate locally, while being Docker-ready.
7. Do not introduce infrastructure or AI components unless they are needed.

---

## 2. V1 System Boundary

### 2.1 Shared CRM database

The existing CRM/application PostgreSQL database remains shared/general across clients.

It already contains or will contain operational application data such as:

- users
- leads
- calls
- call summaries
- follow-ups
- site visits
- lead quality
- other existing CRM/voice-agent metadata

The RAG project must not redesign the CRM database.

Codex must inspect the existing application/database and integrate with existing conventions rather than assuming a new CRM schema.

### 2.2 Per-client RAG database

Each client/agency gets an individual PostgreSQL database with pgvector for its RAG/property knowledge.

Initial architecture:

```text
PostgreSQL server/instance
├── crm_db
├── rag_client_001
├── rag_client_002
└── rag_client_003
```

For the first few clients these databases may live on the same PostgreSQL server/instance.

This does NOT mean one PostgreSQL server per client.

The design must not hard-code assumptions that prevent moving a client's RAG database to another PostgreSQL instance later.

### 2.3 Voice agent database access

The voice agent may connect to:

1. Shared CRM DB for operational read/write actions.
2. Its client's RAG DB for property retrieval.

The RAG ingestion system does not own voice-agent recommendation logic.

---

## 3. Architectural Principle

Use:

> Rich ingestion model, simple retrieval/read model.

The ingestion system may use multiple internal structures for sources, extraction, canonical entities, provenance, staging, jobs, etc.

The voice agent must not need to understand or traverse that ingestion machinery during a live call.

The live RAG read model must be deliberately denormalized for hybrid retrieval.

---

## 4. Supported V1 Sources

Primary V1 uploaded formats:

- PDF
- Excel
- CSV
- DOC/DOCX as supported by the chosen parser/application implementation
- ZIP may remain supported depending on the existing implementation

Database connectors and external API connectors are future considerations, not V1 priorities.

### 4.1 Upload size

Maximum size per file:

```text
50 MB
```

### 4.2 Encrypted/password-protected documents

Reject password-protected/encrypted documents.

Do not implement password input/decryption workflows in V1.

### 4.3 External links

Only ingest physically uploaded content.

Do not follow URLs embedded inside brochures/documents.

No external crawling.

### 4.4 ZIP

The existing application has some ZIP support.

Codex must inspect it before deciding how to retain/refactor it.

If ZIP support is retained, treat ZIP as a transport/batch container, not as a property knowledge document itself.

Do not invent additional ZIP behavior beyond what integrates cleanly with the final batch/source model.

---

## 5. File Storage

V1 uses local filesystem storage.

The storage root/path must be configurable so it can be changed through environment/configuration.

The implementation must be Docker-ready and allow the storage directory to be mounted as persistent storage.

Do not couple ingestion logic directly to local filesystem operations. Keep storage behind a small abstraction so a future implementation could use another storage backend without rewriting the ingestion pipeline.

Do not implement a cloud storage migration in V1.

---

## 6. Duplicate Detection

Use SHA-256 of the uploaded file bytes.

An exact duplicate file must not be reprocessed.

Different filenames do not make identical bytes a new file.

If the previous attempt for that file failed, re-upload/retry behavior may allow processing as appropriate to the existing source/job state.

The user must receive a clear duplicate indication when an already-uploaded successful file is detected.

---

## 7. Source Identity and Versions

Filename is metadata, not identity.

Each logical uploaded source has an internal stable `source_id`.

Example:

```text
source_id: SRC-001

v1: shivalik-brochure.pdf
        ↓ replace
v2: Shivalik_Final_2026.pdf
```

Replacement is based on `source_id`, so a replacement file may have a completely different filename.

The latest successfully published source version is the active version.

---

## 8. Upload Batches

A single ingestion batch may contain multiple files.

Example:

```text
Batch
├── brochure.pdf
├── prices.xlsx
├── floor-plans.pdf
└── specifications.docx
```

Files in the same batch may be used together during entity resolution/reconciliation.

For example, one file may contain a project code while another contains the project name/details.

### 8.1 Batch is not the transaction boundary

Files have independent processing/publishing outcomes.

Example:

```text
brochure.pdf        SUCCESS
prices.xlsx         SUCCESS
floor-plans.pdf     FAILED
specifications.docx SUCCESS
```

Successful files may publish even when another file in the batch fails.

The failed file remains failed.

---

## 9. Structured vs Document Failure Behavior

### 9.1 Structured sources

For structured data such as Excel/CSV, safe independent records may partially succeed when record boundaries and validity are reliable.

Do not discard valid independent rows solely because another independent row is invalid.

### 9.2 Document-oriented sources

For PDF/DOCX-style documents where facts may depend on surrounding pages/sections, default to file-level atomicity.

If the file cannot be reliably processed, do not publish partial document-derived knowledge.

---

## 10. Internal Job Queue

Do not perform full ingestion inside the upload HTTP request.

Use an internal durable queue based on the existing PostgreSQL/RAG infrastructure rather than adding Redis/RabbitMQ/Celery for V1.

Conceptual flow:

```text
Upload
  ↓
Physical file saved
  ↓
Source/batch/job metadata created
  ↓
QUEUED
  ↓
Background processing
  ↓
PROCESSING
  ↓
COMPLETED or FAILED
```

Only one logical ingestion job should run at a time per RAG store/client in V1.

Internal implementation may optimize safe sub-steps later, but concurrent logical ingestion jobs are not required.

The user wants an internal queue system with cron or a trigger. The exact worker trigger/polling implementation may be chosen after Codex inspects the existing application/runtime. Do not add unnecessary queue infrastructure.

### 10.1 Automatic retry

Do NOT automatically retry failed ingestion jobs in V1.

Expose a frontend Retry action.

A retry should use the already-stored physical file when possible; the user should not need to upload it again merely because processing failed.

Permanent rejection conditions such as unsupported/encrypted/oversized files should be surfaced clearly.

---

## 11. Processing Status and Logs

The system must expose useful stage-level processing status.

Conceptual stages include:

```text
UPLOAD
DUPLICATE_CHECK
QUEUED
PARSING
OCR
EXTRACTION
ENTITY_RESOLUTION
NORMALIZATION
RECONCILIATION
SEARCH_REPRESENTATION_GENERATION
EMBEDDING
STAGING
PUBLISH
COMPLETED
FAILED
```

These are conceptual stage names, not a mandated final enum.

Codex may adapt names to existing app-wide conventions.

For failures, store enough information to identify:

- source/file
- batch/job
- failed stage
- error message/details useful for debugging
- timestamps
- processing duration where useful

---

## 12. Audit / Activity History

Processing logs and audit/activity history are separate concepts.

Audit lifecycle events must cover relevant actions such as:

- upload
- duplicate rejection
- batch membership
- queued
- processing/status changes
- processing failure
- retry
- successful publication
- source replacement
- old source version retirement
- physical old-file deletion
- explicit source deletion

Where applicable store:

- source identifier
- user ID
- timestamp
- action
- relevant status/error metadata

The existing application user ID must be stored so the uploader/person performing relevant source actions is traceable.

Do not create a separate RAG user system.

Audit metadata remains after physical source deletion.

---

## 13. Extraction Strategy

Use:

> Deterministic extraction first. AI only where deterministic processing is insufficient.

Conceptual routing:

```text
FILE
 ↓
detect format
 ↓
┌──────────────────────────────────────────┐
│ CSV/XLSX → deterministic structured parser
│ DOCX     → native document parser
│ PDF      → document/layout parser
│ scanned/visual PDF → OCR/vision when needed
└──────────────────────────────────────────┘
 ↓
raw extraction
 ↓
AI-assisted interpretation only where needed
 ↓
entity resolution
 ↓
normalization
 ↓
canonical property state
```

Do not send every document/page to an LLM by default.

### 13.1 Excel/CSV

Prefer deterministic parsing.

Use AI only when interpretation/entity resolution is actually needed.

### 13.2 DOCX

Use normal/native document parsing for text/tables/layout that can be extracted deterministically.

### 13.3 PDF

Use deterministic digital PDF extraction where possible.

Use OCR/vision only for scanned pages or information that ordinary extraction cannot reliably capture.

### 13.4 Cross-page / cross-sheet structures

When evidence is reliable, reconstruct logically continuous tables/records that span:

- multiple PDF pages
- multiple Excel sheets

Do not blindly treat every page/sheet as an unrelated source of facts.

---

## 14. AI-Assisted Extraction

V1 intends to use a Mistral free/low-cost model for AI-assisted extraction/entity resolution.

Keep AI usage behind a small provider abstraction so ingestion architecture is not permanently tied to one provider/model.

Near-zero cost is a V1 constraint.

External APIs are allowed when they materially improve accuracy, but deterministic/local processing should be preferred where it performs adequately.

Do not require a GPU.

Internet may be required for external AI APIs when selected.

---

## 15. Raw Extraction Retention

Retain these layers:

```text
Original source file
      ↓
Raw extraction
      ↓
Canonical property state
      ↓
Search/read representations
```

Raw extraction should be retained so parsing/debugging/reconciliation can be inspected without immediately repeating expensive document processing.

### 15.1 Extracted images

Do not separately persist every image extracted from PDF/DOCX in V1.

Keep the original document and extracted textual/structured interpretation.

If an image is itself uploaded as a supported source in the future, that is a separate concern.

---

## 16. Grounding Rule

The system must extract explicit facts, not invent property characteristics.

This applies to deterministic processing and AI-assisted extraction.

Example:

Source:

```text
DPS Bopal - 700 m
```

Allowed:

```text
nearby place = DPS Bopal
distance = 700 m
```

Not allowed:

```text
family_friendly = true
```

unless the source explicitly states that.

### 16.1 Subjective information

Subjective facts may be stored only when explicitly stated in the source.

Do not independently infer:

- spacious
- premium
- excellent ventilation
- good investment
- family friendly
- best value
- similar subjective claims

### 16.2 Floor plans

Extract explicit labels/dimensions such as:

- room dimensions
- balcony dimensions
- labels
- explicit unit/configuration facts

Do not infer subjective layout characteristics from visual appearance.

### 16.3 Charts/graphs

Extract explicit labels/text/numbers when reliable.

Do not infer exact numerical values from visual graph geometry when the underlying number is not explicitly stated.

---

## 17. Uncertainty and Document Usability

Do not require perfect extraction.

If a few optional fields are unclear:

```text
omit uncertain field
log warning
continue with reliable facts
```

If the majority/core structure/content of the document cannot be understood reliably:

```text
reject/fail the file
```

Do not invent a fixed confidence percentage in V1.

Do not assume model/parser confidence scores are perfectly calibrated.

Critical identity failures may make a record/file unusable.

Accepted extracted facts should retain extraction confidence/quality information where available.

---

## 18. Canonical Entity Model

The canonical model must support:

1. Project
2. Project configuration
3. Individual property

Project is NOT mandatory.

### 18.1 Project hierarchy

Example:

```text
Shivalik Sky
├── project-level facts
├── amenities
├── location
├── specifications
└── configurations
    ├── 2 BHK
    │   ├── 1250 sqft
    │   └── 1350 sqft
    └── 3 BHK
        ├── 1650 sqft
        └── 1850 sqft
```

This hierarchy is preferred over flattening every configuration into unrelated records.

### 18.2 Configuration identity

BHK + area alone is not always a unique identity.

Multiple variants may share the same BHK and area.

Configuration identity must conservatively use available signals such as configuration/type/name and other explicit differentiators.

### 18.3 Individual property

The system must support independent/resale/listing properties that do not belong to a named project.

Example:

```text
3 BHK Apartment
South Bopal
1650 sqft
₹92L
2 balconies
Ready to move
```

Do not create a fake project merely to fit the schema.

---

## 19. Conservative Entity Resolution

Maximum accuracy is more important than aggressive deduplication.

### 19.1 Projects/configurations

Use multiple signals where available.

Do not merge entities merely because one weak field matches.

### 19.2 Individual properties

A stable listing/property ID cannot be assumed.

Conservatively identify potential duplicates using combinations of available information such as:

- normalized location/address
- project/society/developer when available
- property type
- BHK
- area type/value
- price
- other distinctive explicit attributes

If confidence is insufficient:

> Keep entities separate rather than risk merging two different properties.

---

## 20. Linking Individual Properties to Projects

An individual property may be linked to a project/configuration only when relationship confidence is very high.

Example:

```text
Shivalik Sky
├── configurations
└── individual listing X
```

If confidence is not very high, keep the individual property independent.

---

## 21. Inheritance / Parent Context

Project-level facts may provide context to configurations and very-high-confidence linked individual properties.

Keep this simple.

Do NOT copy project facts into every canonical child record.

Use:

> Store facts once. Store relationships. Generate contextual search representations.

Inherited/search context must remain distinguishable from direct facts through provenance/relationships.

Do not let inherited context masquerade as information explicitly stated in the child's source.

---

## 22. Core + Dynamic Canonical Data

Use typed/standardized fields for common recommendation/filtering data.

Use JSONB for unknown/uncommon/dynamic attributes.

Core means:

> Standardized when available, not mandatory.

Missing fields must remain missing rather than being invented.

### 22.1 Core identity

Include concepts such as:

- entity type
- name
- project name/reference when applicable
- configuration name/type when applicable

### 22.2 Property characteristics

Include common fields such as:

- property type
- BHK
- bedrooms
- bathrooms
- balconies

### 22.3 Location

Include:

- country/state/city/locality hierarchy when available
- address/original location text

### 22.4 Price

Support common normalized concepts such as:

- price min
- price max
- currency

Do not assume an unspecified price is base price/all-inclusive price/etc.

### 22.5 Area

Keep different area types separate:

- carpet area
- built-up area
- super built-up area
- plot area

Do not collapse them into one generic area field.

Where practical preserve:

- original value
- original unit
- normalized value
- normalized unit

Deterministic unit conversion is allowed.

### 22.6 Status

Include standardized fields where explicitly available, such as:

- possession status
- possession date

### 22.7 Physical/common recommendation fields

Where available:

- floor
- total floors
- facing
- furnishing status
- parking

### 22.8 Project identity

Where explicitly available:

- developer name
- RERA/project registration ID

### 22.9 Dynamic JSONB

Unknown/special fields belong in flexible canonical JSONB.

Examples:

```json
{
  "private_foyer": "85 sqft",
  "flooring": "Italian Marble",
  "water_supply": "24x7"
}
```

Dynamic JSONB must not become the primary runtime search mechanism for common filters.

---

## 23. Amenities

Amenities are important for recommendations.

Normalize clear equivalents into a controlled amenity vocabulary while preserving original source wording.

Example:

```text
fitness centre
gymnasium
gym
   ↓
gym
```

Only normalize clear equivalents.

Do not infer amenities.

Unknown/special amenities must be preserved rather than discarded.

Do not create unnecessary relational complexity solely for amenities in V1.

---

## 24. Nearby Places / Connectivity

Explicit nearby places/connectivity data should be preserved.

Example:

```text
name: DPS Bopal
category: school
distance: 0.7
unit: km
```

Only use information explicitly present in uploaded content.

No Maps lookup.

No inferred distances.

Keep the canonical representation flexible/simple rather than building a complex dedicated subsystem for V1.

Nearby/connectivity information may be compiled into location/connectivity search representations.

---

## 25. No Coordinates / Geocoding

Do not add geocoding in V1.

Do not make latitude/longitude part of the V1 canonical requirement.

Location remains textual/hierarchical.

---

## 26. Conflict Reconciliation

Reconciliation is field-level, not whole-document replacement.

Example:

Older brochure:

```text
price = ₹85L
area = 1650 sqft
balconies = 2
```

Newer active Excel:

```text
price = ₹90L
```

Canonical state:

```text
price      = ₹90L
area       = 1650 sqft
balconies  = 2
```

The newer source overrides only the conflicting fact.

Non-conflicting facts from older active sources remain.

### 26.1 V1 precedence rule

For conflicting facts:

> Newest successfully published active source wins.

Use upload/publication ordering according to the implementation's source version metadata consistent with this rule.

Do not implement source-authority scoring in V1.

Do not automatically prefer brochure vs Excel vs PDF based on file type.

Do not let an LLM decide which source is more trustworthy.

---

## 27. Provenance

Canonical facts must remain traceable to their sources.

Where possible preserve details such as:

- source ID/version
- original filename
- page number
- sheet
- row
- section/block
- original extracted value/text
- extraction method
- extraction confidence/quality

A canonical entity/search record may have multiple provenance references.

Example:

```text
3 BHK Type A
1650 sqft
₹85L
2 balconies

price:
  prices.xlsx / Sheet 2 / Row 17

area:
  brochure.pdf / Page 12

balconies:
  floorplans.pdf / Page 4
```

Provenance must support future debugging/admin citation needs.

The voice agent does not have to speak citations to customers, but searchable results should expose enough source references that they can be traced.

---

## 28. Source Replacement

When the user wants to update a source, V1 uses source replacement rather than manual property-field editing.

Flow:

```text
existing active source/version
      ↓
user selects Replace
      ↓
upload replacement
      ↓
process replacement fully
      ↓
stage new derived state
      ↓
if success:
    publish new state
    retire old source version
    remove obsolete old derived data
    physically delete old file
if failure:
    keep old source/version live
    mark new processing attempt failed
```

Never delete the active old file/data before the replacement has successfully processed/published.

Filename may change during replacement.

---

## 29. Explicit Source Delete

When a user deletes a source:

1. Identify affected canonical entities.
2. Remove that source's contribution.
3. Reconstruct affected entities from remaining active sources.
4. Regenerate affected search representations/embeddings/FTS data.
5. Publish reconstructed state safely.
6. Remove deleted-source raw/derived data.
7. Physically delete the source file.
8. Keep lightweight audit metadata.

If no remaining source supports an entity/fact, remove it from live canonical/searchable knowledge.

If another active source independently supports the same fact, that fact remains.

---

## 30. Manual Editing

Manual editing of canonical property fields is OUT OF SCOPE for V1.

There is no manual-override precedence system in V1.

Users update knowledge by replacing source files.

---

## 31. User-Facing Reprocess

A generic user-facing Reprocess operation is OUT OF SCOPE for V1.

Development/operational migrations may still rebuild derived data when the system changes, but do not build a product reprocess workflow in V1.

---

## 32. Canonical Search Text

Do not embed arbitrary raw extracted document chunks as the primary knowledge representation.

Use:

```text
raw source
   ↓
canonical property state
   ↓
clean canonical search text
   ↓
embedding + keyword index
```

The canonical text should include normalized values while retaining useful original terminology where appropriate.

Raw extraction remains available separately for provenance/debugging.

---

## 33. Search/Read Model

The voice agent should primarily retrieve from a deliberately simple denormalized read model.

Conceptually, searchable records may contain fields such as:

```text
id
entity_id
entity_type

project_id
configuration_id

section_type
content

embedding
search_vector

priority

city
locality
property_type
bhk
price_min
price_max
area_sqft
possession_status

metadata JSONB

embedding model/version metadata

provenance references
```

This is architectural intent, not a mandatory exact SQL table definition.

Codex must design the final schema around the existing application and these requirements.

### 33.1 Why denormalize

The voice agent should NOT need to:

```text
query projects
→ configurations
→ amenities
→ nearby places
→ attributes
→ sources
→ manually assemble property context
```

during a live call.

Instead it should be able to search the read model and receive relevant canonical content plus IDs/filter metadata.

---

## 34. High-Value Filter Fields in Read Model

Duplicate a small set of common recommendation/filter fields onto searchable records where useful.

Examples:

- city
- locality
- property type
- BHK
- price min/max
- normalized relevant area
- possession status

This deliberate denormalization is acceptable.

Do not duplicate every canonical field.

Uncommon attributes can remain in metadata/canonical storage.

---

## 35. Property-Aware Search Sections

Do not use arbitrary fixed-token chunking as the primary strategy.

Generate property-aware semantic sections such as:

```text
PROJECT_CORE
CONFIGURATION_CORE
PROPERTY_CORE
AMENITIES
LOCATION_CONNECTIVITY
SPECIFICATIONS
PRICING_DETAILS
OTHER_DYNAMIC
```

Not every entity must have every section.

Exact section names may be adjusted during implementation, but the strategy must remain property-aware rather than blind token slicing.

---

## 36. Parent Context in Child Search Representations

Child search text should contain compact identity/parent context.

Bad:

```text
Swimming pool, gym, EV charging
```

Better:

```text
Shivalik Sky | South Bopal | 3 BHK | Type A

Amenities:
Swimming pool, gym, EV charging
```

Do not duplicate the complete parent/project content into every child representation.

Store IDs separately as metadata.

---

## 37. Hybrid Search Preparation

The ingestion system prepares data for three retrieval mechanisms:

### 37.1 Semantic

PostgreSQL + pgvector embeddings.

### 37.2 Keyword

PostgreSQL full-text/keyword-search representation/index.

### 37.3 Exact filtering

Denormalized common filter metadata on the live read model.

The actual hybrid retrieval algorithm, ranking, reranking, recommendation logic, and voice-agent query interpretation are outside the RAG ingestion system's V1 responsibility.

---

## 38. Multilingual Requirements

The knowledge/retrieval ecosystem must consider:

- English
- Hindi
- Marathi
- Gujarati
- Romanized/mixed Indic language queries

V1 must NOT generate AI-translated aliases for every property.

Start with:

```text
original/canonical content
+
deterministic normalization
+
multilingual embeddings
+
keyword index
```

Proper nouns, project names, locations, identifiers, etc. must preserve their original exact values.

Do not replace original names with normalized/generated variants.

Only add transliteration/alias generation later if benchmarks demonstrate a measurable retrieval gap.

---

## 39. Embedding Model Selection

Do NOT hard-code the final embedding model before benchmarking.

Embedding model selection is a required architecture/implementation step.

Benchmark candidate multilingual embedding models using representative real-estate data and queries covering:

- English
- Hindi
- Gujarati
- Marathi
- Romanized Hindi/Gujarati/Marathi
- mixed-language queries
- project names
- exact locations
- amenities
- prices
- BHK
- areas
- configurations

Evaluate at least:

- retrieval accuracy
- multilingual behavior
- query-embedding latency
- cost
- model/vector dimensions

Accuracy is the primary goal.

The architecture should allow changing the embedding provider/model without rewriting the ingestion application, while recognizing that changing embedding models requires re-embedding existing knowledge.

---

## 40. Query Embedding Note

Property embeddings are mostly generated during ingestion/update.

However semantic retrieval also requires embedding the user's runtime query with the compatible embedding model.

Therefore embedding provider/model choice can affect voice-agent runtime latency.

This does not change the RAG ingestion system boundary, but it must be considered during embedding-model benchmarking.

---

## 41. Embedding Model Change / Full Re-Embedding

When the active embedding model changes:

> Re-embed all active searchable knowledge for that client.

Do not mix incompatible embedding models in one active similarity index.

Retain metadata sufficient to identify the embedding model/version/dimension as needed.

Re-embedding can use retained canonical search text; it should not require reparsing every original document solely to change the embedding model.

### 41.1 Atomic re-embedding

Keep old embeddings live until the complete replacement embedding set succeeds.

Conceptual flow:

```text
embedding set V1 LIVE
      ↓
generate full V2 in staging
      ↓
success?
├── NO  → V1 remains live
└── YES → atomically activate V2, retire V1
```

Never leave the voice agent with a partially re-embedded active knowledge base.

---

## 42. Staging and Publishing

Do NOT use two separate physical live/temp databases for V1.

Use versioned/staged data inside the per-client RAG database.

Reason:

- expected V1 scale is small
- two physical databases add migrations/connections/synchronization/cleanup complexity
- the same safety can be achieved by staged/versioned publishing

The key rule:

> Old searchable state remains live while new state is being prepared.

Only successfully completed affected state becomes live.

### 42.1 Affected-property publishing

For normal source updates, publish affected entities/property knowledge rather than rebuilding unrelated inventory.

New successfully processed information updates affected entities; unrelated existing live entities remain unchanged.

---

## 43. Expected Scale

Expected initial maximum:

```text
~1,000 properties per client
```

Do not optimize V1 for hundreds of thousands/millions of properties.

Do not add distributed vector infrastructure.

For pgvector index/search strategy, benchmark exact search before adding approximate ANN indexing such as HNSW.

Accuracy is the priority.

The final pgvector index type is intentionally NOT fixed in this document.

---

## 44. LangGraph

Python is the implementation language for the RAG ingestion system.

LangGraph is optional.

It may be used for ingestion workflow orchestration if it materially simplifies:

- state transitions
- branching
- resumability
- failure handling
- workflow orchestration

Do not use LangGraph merely because the project involves AI.

If plain Python services/workers are simpler and reliable, use them.

---

## 45. Deployment

V1 is:

- local-first
- Docker-ready
- CPU-capable
- no mandatory GPU

External AI APIs may be used when they provide a worthwhile accuracy/cost benefit.

Keep operating cost as close to free as practical.

Do not bind the architecture to Render, Railway, Vercel, AWS, or another specific cloud provider.

---

## 46. Basic Security Only

V1 includes basic production-safe upload/security controls.

Include basics such as:

- allowed file-type validation
- 50 MB maximum file size
- safe/sanitized file paths/names
- path traversal prevention
- do not execute uploaded macros/content
- secrets/DB credentials via configuration/environment
- existing user identity in source/audit actions

Advanced security/compliance is outside V1.

Do not expand V1 into malware sandboxing, advanced compliance, encryption-at-rest programs, etc.

---

## 47. Existing Upload Implementation

The current application has a simple upload/status implementation:

```text
user uploads file
→ store file at configured location
→ update status
```

It currently treats each file individually and does not implement the required hierarchy/lifecycle.

This existing implementation is a starting point, NOT an architectural constraint.

Codex may refactor it to support:

- batches
- stable source identity
- source versions
- replacement
- deletion
- queueing
- processing stages
- audit
- reconciliation
- staging/publishing

Reuse existing code where it remains useful and compatible.

Follow existing application-wide conventions for tables, APIs, error responses, naming, configuration, frontend patterns, etc., after inspecting the codebase.

---

## 48. What the Voice Agent Needs From RAG

The RAG store must be able to provide property metadata/details such as, when explicitly available:

- square footage/area
- BHK/property type
- price
- balconies
- amenities
- location
- possession/status
- configuration details
- dynamic/special property details
- nearby/connectivity information
- other grounded canonical facts

The RAG system itself does NOT decide which property is the best recommendation.

It prepares accurate searchable knowledge.

---

## 49. V1 Non-Goals / Out of Scope

Do NOT implement these as part of V1 unless required to make an explicitly included feature work:

- manual canonical property editing
- manual override precedence
- human-review workflow
- external URL crawling
- geocoding
- Maps APIs
- latitude/longitude canonical modeling
- database source connectors
- external API source connectors
- automatic ingestion retry
- user-facing generic reprocess feature
- recommendation scoring
- property ranking
- investment-potential scoring
- similarity/recommendation engine logic
- CRM redesign
- database backup strategy
- HA/replication/disaster recovery
- advanced security/compliance
- automatic multilingual alias generation
- unnecessary large-scale optimization beyond ~1,000 properties/client
- separate physical staging/temp RAG database

Database/API source connectors remain a future consideration. Do not deliberately design V1 in a way that makes future connectors impossible.

---

## 50. Decisions Intentionally Left Open

Do not silently choose these before inspecting/benchmarking as required:

### 50.1 Embedding model

Must be benchmarked for the required languages/real-estate queries.

### 50.2 pgvector index strategy

Exact vs HNSW/other approximate index must be decided based on the expected V1 scale and benchmarks.

### 50.3 Exact parser/OCR/vision libraries

Choose deterministic/local tools that satisfy accuracy and cost constraints. Use external APIs only where justified.

### 50.4 Exact confidence thresholds

Do not invent a universal numeric threshold. Use reliable extraction/entity-resolution rules and document usability criteria.

### 50.5 LangGraph

Use only if it simplifies the final ingestion workflow.

### 50.6 Exact queue trigger

The user wants an internal queue using cron/trigger-style processing. Choose the simplest reliable mechanism after inspecting the existing application/runtime.

### 50.7 ZIP implementation

Inspect current support and integrate it cleanly or simplify it as appropriate.

### 50.8 Exact SQL/table names

Follow the existing application's database conventions while implementing the architecture described here.

---

## 51. Required End-to-End Upload Flow

Conceptual normal upload:

```text
User uploads one or more files
        ↓
Validate basic file constraints
        ↓
SHA-256 duplicate check
        ↓
Store physical file
        ↓
Create/update batch + source + job metadata
        ↓
QUEUED
        ↓
Worker claims next job
        ↓
Detect format
        ↓
Deterministic parsing
        ↓
OCR/vision only when needed
        ↓
Retain raw extraction
        ↓
AI-assisted interpretation only when needed
        ↓
Extract grounded entities/facts
        ↓
Cross-file entity resolution/reconciliation
        ↓
Normalize canonical property state
        ↓
Apply field-level newest-active-source conflict rule
        ↓
Generate property-aware canonical search representations
        ↓
Generate keyword-search representation
        ↓
Generate embeddings
        ↓
Stage affected live-state changes
        ↓
Publish successful changes
        ↓
COMPLETED
```

If processing fails before publish:

```text
FAILED
→ store stage/error
→ do not corrupt existing live knowledge
→ user may press Retry
```

---

## 52. Required Replacement Flow

```text
User selects existing source
        ↓
Replace
        ↓
Upload new file
        ↓
Validate + duplicate handling
        ↓
Keep old source/version LIVE
        ↓
Process new version
        ↓
Reconcile affected entities
        ↓
Generate new search/index state
        ↓
Stage
        ↓
SUCCESS?
├── NO
│   ├── mark replacement attempt failed
│   └── old version remains live
│
└── YES
    ├── publish new affected state
    ├── retire old source version
    ├── remove obsolete old derived data
    └── physically delete old file
```

---

## 53. Required Delete Flow

```text
User deletes source
        ↓
Find affected entities/facts
        ↓
Remove source contribution
        ↓
Reconstruct affected canonical entities
from remaining active sources
        ↓
Regenerate affected canonical search text
        ↓
Regenerate affected keyword/vector data
        ↓
Stage reconstructed state
        ↓
Publish
        ↓
Remove deleted-source raw/derived data
        ↓
Physically delete source file
        ↓
Retain lightweight audit history
```

Facts supported independently by another active source remain.

Entities with no remaining supporting source are removed from live knowledge.

---

## 54. Required Full Re-Embedding Flow

```text
Embedding model changes
        ↓
Keep current embedding set LIVE
        ↓
Generate embeddings for ALL active canonical
search representations into staged version
        ↓
All succeed?
├── NO  → current embedding set remains live
└── YES → atomically activate new embedding set
           and retire old set
```

Do not mix embedding models in the active search space.

---

## 55. Accuracy Principles for Codex

When implementation choices conflict, use these priorities:

1. Never fabricate property facts.
2. Preserve explicit source meaning.
3. Prefer keeping two uncertain entities separate over incorrectly merging them.
4. Prefer deterministic parsing for structured information.
5. Use AI for interpretation only where it adds value.
6. Newest successfully published active source wins only the conflicting field/fact.
7. Preserve non-conflicting facts from other active sources.
8. Preserve provenance.
9. Keep old live state available until replacement/staged state is successfully publishable.
10. Keep voice-agent retrieval simple.
11. Avoid V1 complexity that does not improve these goals.

---

## 56. Codex Implementation Instructions

Before changing code, Codex must inspect the existing application and understand:

- current backend/frontend structure
- existing file upload flow
- existing file/status tables
- existing user identity/auth flow
- existing database conventions
- existing API response/error conventions
- existing configuration/environment patterns
- existing Docker setup if present
- current ZIP handling
- any existing RAG/embedding code
- existing application-wide UI/table patterns

Then perform a gap analysis against this specification.

Do not redesign unrelated CRM functionality.

Do not introduce requirements that are not present in this document merely because they are common in other RAG systems.

Where this document intentionally leaves an implementation choice open, choose the simplest solution that satisfies:

- accuracy
- near-zero V1 cost
- local/Docker operation
- current ~1,000-property/client scale
- maintainability
- existing application conventions

If an implementation decision materially changes the architecture or product behavior described here, stop and surface that decision instead of silently changing the requirement.

---

## 57. Final V1 Architecture

The approved V1 architecture is:

> Per-client PostgreSQL + pgvector RAG databases; a shared existing CRM PostgreSQL database; local configurable source storage; batch-aware stable source/version lifecycle; PostgreSQL-backed internal single-job ingestion queue; deterministic-first parsing with selective Mistral-assisted extraction; grounded canonical project/configuration/individual-property modeling; field-level source reconciliation; provenance and audit logging; versioned/staged publishing; property-aware canonical search representations; multilingual semantic + keyword-search preparation; denormalized high-value filter metadata for the voice agent; and atomic full re-embedding when the embedding model changes.

The RAG system is a property knowledge ingestion/indexing system.

The voice agent remains responsible for retrieval behavior, ranking/reranking, recommendations, conversations, and CRM operations.
