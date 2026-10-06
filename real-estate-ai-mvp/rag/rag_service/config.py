"""Settings for the knowledge service (API, worker and migrate share one image and one config)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- storage
    rag_database_url: str = "postgresql://rag:rag@localhost:5432/estraos_knowledge"
    rag_storage_path: Path = Path("./storage")
    rag_max_upload_bytes: int = 50 * 1024 * 1024
    db_pool_min: int = 2
    db_pool_max: int = 10

    # ---- auth. The CRM uses RAG_SERVICE_TOKEN for everything except live-call retrieval;
    # the voice agent uses RAG_VOICE_TOKEN, which is bound to exactly one workspace.
    rag_service_token: str = ""
    rag_voice_token: str = ""
    rag_voice_workspace_id: int = 0

    # ---- providers. fake runs offline: a deterministic hashing embedder and a text-only parser.
    provider_mode: Literal["live", "fake"] = "live"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    cohere_api_key: str = ""

    # ---- parsing
    parser_provider: Literal["openai", "mistral"] = "openai"
    # gpt-4.1-mini: same transcription quality as gpt-4o-mini on brochure pages, ~3.5k instead of
    # ~37k input tokens per page (gpt-4o-mini bills images at a multiple), so ~1/3 of the cost and a
    # tenth of the tokens-per-minute rate limit.
    parser_model: str = "gpt-4.1-mini"
    mistral_ocr_model: str = "mistral-ocr-latest"
    parse_concurrency: int = 4
    parse_max_retries: int = 3
    parse_dpi: int = 144
    # Pages parsed below this confidence are still published, but flagged in the status response.
    low_confidence_threshold: float = 0.6
    classifier_model: str = "gpt-4o-mini"

    # ---- extraction of projects and listings for the CRM (any OpenAI-compatible API; Groq by default).
    # Without a key, listing tables are still read in code; other pages are skipped.
    groq_api_key: str = ""
    extraction_base_url: str = "https://api.groq.com/openai/v1"
    extraction_model: str = "openai/gpt-oss-120b"

    # ---- embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    embedding_batch_size: int = 256

    # ---- chunking
    chunk_target_tokens: int = 350
    chunk_max_tokens: int = 450
    chunk_min_tokens: int = 250
    chunk_overlap_ratio: float = 0.15
    table_max_tokens: int = 800
    # Tables with more data rows than this also get one TABLE_ROW chunk per row.
    table_row_chunk_min_rows: int = 6

    # ---- retrieval
    reranker: Literal["bge", "cohere", "none"] = "bge"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    cohere_rerank_model: str = "rerank-v3.5"
    rerank_budget_ms: float = 150.0
    # Live-call path only: past this, answer from keyword/name search without the query embedding.
    voice_embed_budget_ms: float = 300.0
    rerank_candidates: int = 20
    candidate_pool: int = 30
    rrf_k: int = 60
    query_cache_size: int = 2048
    rewrite_model: str = "gpt-4o-mini"
    rewrite_on_voice: bool = False
    # Query-focused excerpt per chunk on the live-call path (see retrieve/snippet.py).
    voice_snippet_chars: int = 900

    # ---- worker
    worker_poll_s: float = 1.0
    job_max_attempts: int = 5
    job_backoff_s: float = 10.0

    # USD per 1M tokens, for per-document cost accounting.
    price_parse_input_per_m: float = 0.15
    price_parse_output_per_m: float = 0.60
    price_embed_per_m: float = 0.02

    @field_validator("embedding_dim")
    @classmethod
    def _dim(cls, value: int) -> int:
        if not 1 <= value <= 4000:
            raise ValueError("EMBEDDING_DIM must be between 1 and 4000")
        return value

    @property
    def vector_type(self) -> str:
        """HNSW indexes `vector` up to 2000 dimensions; above that, store half precision."""
        return "vector" if self.embedding_dim <= 2000 else "halfvec"

    @property
    def effective_embedding_model(self) -> str:
        """The model name recorded on every chunk and checked against the index."""
        return "fake-hashing-v1" if self.provider_mode == "fake" else self.embedding_model

    @property
    def request_dimensions(self) -> int | None:
        """text-embedding-3-* can shorten their output; ask for exactly what the index stores."""
        return self.embedding_dim if self.embedding_model.startswith("text-embedding-3") else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
