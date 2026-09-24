CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS rag_schema_version (version integer PRIMARY KEY);
INSERT INTO rag_schema_version VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS rag_store (
  id integer PRIMARY KEY CHECK (id=1), workspace_id bigint NOT NULL,
  active_embedding_set uuid, publication_sequence bigint NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rag_batches (
  id uuid PRIMARY KEY, created_by bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rag_sources (
  id uuid PRIMARY KEY, active_version uuid, status text NOT NULL,
  created_by bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);
CREATE TABLE IF NOT EXISTS rag_source_versions (
  id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES rag_sources(id),
  batch_id uuid NOT NULL REFERENCES rag_batches(id), version integer NOT NULL,
  filename text NOT NULL, extension text NOT NULL, size_bytes bigint NOT NULL,
  sha256 text NOT NULL, storage_key text, status text NOT NULL,
  raw_extraction jsonb, extracted_entities jsonb, warnings jsonb NOT NULL DEFAULT '[]',
  created_by bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz, publication_order bigint,
  UNIQUE(source_id,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS rag_active_checksum ON rag_source_versions(sha256)
  WHERE status IN ('QUEUED','PROCESSING','ACTIVE');
CREATE TABLE IF NOT EXISTS rag_jobs (
  id uuid PRIMARY KEY, source_id uuid REFERENCES rag_sources(id), version_id uuid REFERENCES rag_source_versions(id),
  kind text NOT NULL CHECK(kind IN ('INGEST','DELETE','REEMBED')), status text NOT NULL,
  stage text NOT NULL, error text, retryable boolean NOT NULL DEFAULT true,
  created_by bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz, finished_at timestamptz, duration_ms bigint, options jsonb NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS rag_one_source_job ON rag_jobs(source_id) WHERE status IN ('QUEUED','PROCESSING');
CREATE UNIQUE INDEX IF NOT EXISTS rag_one_reembed_job ON rag_jobs(kind) WHERE kind='REEMBED' AND status IN ('QUEUED','PROCESSING');
CREATE INDEX IF NOT EXISTS rag_queue ON rag_jobs(created_at) WHERE status='QUEUED';
CREATE TABLE IF NOT EXISTS rag_logs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, job_id uuid NOT NULL REFERENCES rag_jobs(id),
  stage text NOT NULL, message text NOT NULL, details jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rag_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, source_id uuid, version_id uuid, batch_id uuid,
  job_id uuid, actor_id bigint NOT NULL, action text NOT NULL, details jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rag_contributions (
  version_id uuid NOT NULL REFERENCES rag_source_versions(id), entity_id uuid NOT NULL,
  kind text NOT NULL, parent_id uuid, identity jsonb NOT NULL, facts jsonb NOT NULL,
  PRIMARY KEY(version_id,entity_id)
);
CREATE TABLE IF NOT EXISTS rag_entities (
  id uuid PRIMARY KEY, kind text NOT NULL, parent_id uuid, name text, project_name text,
  configuration_name text, property_type text, country text, state text, city text, locality text,
  address text, bhk numeric, bedrooms numeric, bathrooms numeric, balconies numeric,
  price_min numeric, price_max numeric, currency text,
  carpet_area_sqft numeric, built_up_area_sqft numeric, super_built_up_area_sqft numeric, plot_area_sqft numeric,
  possession_status text, possession_date text, floor numeric, total_floors numeric,
  facing text, furnishing_status text, parking jsonb, developer_name text, rera_id text,
  canonical jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rag_embedding_sets (
  id uuid PRIMARY KEY, model_id text NOT NULL, dimensions integer NOT NULL CHECK(dimensions>0),
  status text NOT NULL CHECK(status IN ('STAGING','LIVE','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS rag_one_live_set ON rag_embedding_sets(status) WHERE status='LIVE';
CREATE TABLE IF NOT EXISTS rag_search_records (
  id uuid PRIMARY KEY, embedding_set_id uuid NOT NULL REFERENCES rag_embedding_sets(id), entity_id uuid NOT NULL,
  entity_type text NOT NULL, project_id uuid, configuration_id uuid,
  section_type text NOT NULL, content text NOT NULL, embedding vector NOT NULL,
  search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
  priority integer NOT NULL, city text, locality text, property_type text, bhk numeric,
  price_min numeric, price_max numeric, possession_status text,
  carpet_area_sqft numeric, built_up_area_sqft numeric, super_built_up_area_sqft numeric, plot_area_sqft numeric,
  metadata jsonb NOT NULL, provenance jsonb NOT NULL,
  UNIQUE(embedding_set_id,entity_id,section_type)
);
CREATE INDEX IF NOT EXISTS rag_search_keywords ON rag_search_records USING gin(search_vector);
CREATE INDEX IF NOT EXISTS rag_search_filters ON rag_search_records(embedding_set_id,city,locality,bhk,price_min);
-- Additive amendment: shared model for residential and non-residential assets.
ALTER TABLE rag_entities ADD COLUMN IF NOT EXISTS property_subtype text;
ALTER TABLE rag_entities ADD COLUMN IF NOT EXISTS availability_status text;
ALTER TABLE rag_entities ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE rag_search_records ADD COLUMN IF NOT EXISTS property_subtype text;
ALTER TABLE rag_search_records ADD COLUMN IF NOT EXISTS availability_status text;
INSERT INTO rag_schema_version VALUES (2) ON CONFLICT DO NOTHING;
CREATE OR REPLACE VIEW rag_live_knowledge AS
 SELECT r.id,r.embedding_set_id,r.entity_id,r.entity_type,r.project_id,r.configuration_id,
 r.section_type,r.content,r.embedding,r.search_vector,r.priority,r.city,r.locality,r.property_type,
 r.bhk,r.price_min,r.price_max,r.possession_status,r.carpet_area_sqft,r.built_up_area_sqft,
 r.super_built_up_area_sqft,r.plot_area_sqft,r.metadata,r.provenance,
 s.model_id,s.dimensions AS embedding_dimensions,r.property_subtype,r.availability_status
 FROM rag_search_records r JOIN rag_store store ON store.id=1 AND r.embedding_set_id=store.active_embedding_set
 JOIN rag_embedding_sets s ON s.id=r.embedding_set_id;
CREATE TABLE IF NOT EXISTS rag_file_cleanup (
  storage_key text PRIMARY KEY, source_id uuid, version_id uuid, actor_id bigint NOT NULL,
  last_error text, created_at timestamptz NOT NULL DEFAULT now()
);
