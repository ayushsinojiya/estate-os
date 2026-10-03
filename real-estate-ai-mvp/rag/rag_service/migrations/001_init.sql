-- Knowledge store. One database for every workspace; every row carries workspace_id and every
-- query filters on it. {vector_type}({dim}) is substituted from EMBEDDING_DIM at migrate time.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- The embedding model an index was built with. Mixing models in one index silently ruins
-- similarity scores, so the service refuses to start against a different model.
CREATE TABLE kb_meta (
  key text PRIMARY KEY,
  value text NOT NULL
);

-- One row per uploaded version. source_id is the stable identity of a logical document across
-- versions; the CRM addresses sources by it.
CREATE TABLE kb_documents (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint NOT NULL,
  source_id uuid NOT NULL,
  version integer NOT NULL DEFAULT 1,
  project_id bigint,                       -- NULL: workspace-wide knowledge
  project_name text,
  locality text,
  crm_document_id bigint,                  -- property_documents.id when the CRM owns the record
  crm_file_id bigint,                      -- managed_files.id for Files-page uploads
  title text NOT NULL,
  file_name text NOT NULL,
  mime text NOT NULL,
  size_bytes bigint NOT NULL,
  sha256 char(64) NOT NULL,
  storage_key text NOT NULL,
  doc_type text NOT NULL DEFAULT 'OTHER'
    CHECK (doc_type IN ('BROCHURE','PRICE_SHEET','PAYMENT_PLAN','FAQ','RERA','LEGAL','FLOOR_PLAN','OTHER')),
  doc_type_source text NOT NULL DEFAULT 'auto' CHECK (doc_type_source IN ('auto','crm')),
  languages text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'UPLOADED'
    CHECK (status IN ('UPLOADED','PARSING','EMBEDDING','PUBLISHED','FAILED','UNPUBLISHED','SUPERSEDED','DELETED')),
  error text,
  embedding_model text,
  page_count integer NOT NULL DEFAULT 0,
  chunk_count integer NOT NULL DEFAULT 0,
  parse_input_tokens bigint NOT NULL DEFAULT 0,
  parse_output_tokens bigint NOT NULL DEFAULT 0,
  embed_tokens bigint NOT NULL DEFAULT 0,
  cost_usd numeric(12,6) NOT NULL DEFAULT 0,
  actor_id bigint,
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, source_id, version)
);
CREATE INDEX idx_kb_documents_scope ON kb_documents (workspace_id, project_id, status);
CREATE INDEX idx_kb_documents_source ON kb_documents (workspace_id, source_id, version DESC);
CREATE INDEX idx_kb_documents_crm ON kb_documents (workspace_id, crm_document_id) WHERE crm_document_id IS NOT NULL;
-- Duplicate detection happens on upload (same bytes already live in the workspace). This index is
-- the race backstop: identical bytes can be published only once. A reindex of the same file is
-- fine, because the publish swap supersedes the old version before the new one goes live.
CREATE UNIQUE INDEX uq_kb_documents_published_sha ON kb_documents (workspace_id, sha256)
  WHERE status = 'PUBLISHED';
CREATE INDEX idx_kb_documents_title_trgm ON kb_documents USING gin (title gin_trgm_ops);

-- Parsed markdown per page, kept for review, re-chunking and the low-confidence badge.
CREATE TABLE kb_pages (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint NOT NULL,
  document_id bigint NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
  page_no integer NOT NULL,
  markdown text NOT NULL,
  provider text NOT NULL,
  confidence real NOT NULL DEFAULT 1.0,
  image_sha256 char(64),
  input_tokens integer NOT NULL DEFAULT 0,
  output_tokens integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, page_no)
);
CREATE INDEX idx_kb_pages_document ON kb_pages (workspace_id, document_id);

CREATE TABLE kb_chunks (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint NOT NULL,
  project_id bigint,
  document_id bigint NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
  doc_type text NOT NULL,
  language text,
  page_from integer,
  page_to integer,
  section_path text NOT NULL DEFAULT '',
  chunk_type text NOT NULL CHECK (chunk_type IN ('TEXT','TABLE','TABLE_ROW','FAQ')),
  ordinal integer NOT NULL,
  content text NOT NULL,
  context_header text NOT NULL,
  embedding {vector_type}({dim}) NOT NULL,
  embedding_model text NOT NULL,
  tsv tsvector NOT NULL,
  token_count integer NOT NULL,
  -- Denormalised from the document so retrieval filters on one table. Kept in step with
  -- kb_documents.status inside the same transaction on publish, unpublish and delete.
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','PUBLISHED','UNPUBLISHED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_kb_chunks_scope ON kb_chunks (workspace_id, project_id, status);
CREATE INDEX idx_kb_chunks_document ON kb_chunks (document_id);
CREATE INDEX idx_kb_chunks_embedding ON kb_chunks USING hnsw (embedding {ops}) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_kb_chunks_tsv ON kb_chunks USING gin (tsv);
CREATE INDEX idx_kb_chunks_header_trgm ON kb_chunks USING gin (context_header gin_trgm_ops);

-- Durable job queue. Workers claim with FOR UPDATE SKIP LOCKED, so several workers never take
-- the same job; a failed job is retried with exponential backoff up to max_attempts.
CREATE TABLE kb_jobs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id bigint NOT NULL,
  document_id bigint NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('INGEST')),
  status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED','CANCELLED')),
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  run_after timestamptz NOT NULL DEFAULT now(),
  locked_at timestamptz,
  locked_by text,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_kb_jobs_due ON kb_jobs (status, run_after);
CREATE UNIQUE INDEX uq_kb_jobs_active ON kb_jobs (document_id, kind) WHERE status IN ('QUEUED','RUNNING');
