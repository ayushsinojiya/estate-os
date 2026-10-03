-- Runs once, when the local database container is first created.
CREATE DATABASE estraos_knowledge;
\c estraos_knowledge
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
