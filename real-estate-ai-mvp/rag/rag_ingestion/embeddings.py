"""Local embeddings with an explicit, immutable model and query/document contract.

Changing model_id requires an atomic full re-embedding of the client's store.
No hash/random fallback exists: a failed model load or inference must fail the job.
"""
from __future__ import annotations

import json
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_id: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerProvider:
    """CPU provider. Caller must select a benchmarked model and pinned HF revision.

    E5 requires different literal English prefixes even for non-English inputs.
    Other models use no prefixes unless explicitly configured. The voice agent
    must use embed_queries with precisely the same provider configuration.
    """

    def __init__(
        self,
        model_name: str,
        revision: str,
        *,
        document_prefix: str | None = None,
        query_prefix: str | None = None,
        batch_size: int = 32,
        local_files_only: bool = False,
    ) -> None:
        if not model_name or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Select an explicit model and immutable 40-character Hugging Face revision")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.revision = revision
        self.batch_size = batch_size
        e5 = model_name.startswith("intfloat/multilingual-e5-")
        self.document_prefix = document_prefix if document_prefix is not None else ("passage: " if e5 else "")
        self.query_prefix = query_prefix if query_prefix is not None else ("query: " if e5 else "")
        self._model = SentenceTransformer(
            model_name, revision=revision, device="cpu", trust_remote_code=False,
            local_files_only=local_files_only,
        )
        self.dimension = int(self._model.get_sentence_embedding_dimension())
        self.max_sequence_length = int(self._model.max_seq_length)
        self.model_id = json.dumps({
            "provider": "sentence-transformers-v1", "name": model_name, "revision": revision,
            "dimension": self.dimension, "normalize": True, "max_sequence_length": self.max_sequence_length,
            "document_prefix": self.document_prefix, "query_prefix": self.query_prefix,
        }, sort_keys=True, separators=(",", ":"))

    def _encode(self, texts: list[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings")
        import numpy as np

        inputs = [prefix + text for text in texts]
        # Silent truncation can omit grounded facts. Fail before publishing; the
        # search representation generator should produce smaller semantic sections.
        tokens = self._model.tokenizer(inputs, truncation=False, add_special_tokens=True)["input_ids"]
        if any(len(item) > self.max_sequence_length for item in tokens):
            raise ValueError(f"Canonical search section exceeds model limit of {self.max_sequence_length} tokens")
        result = np.asarray(self._model.encode(
            inputs, batch_size=self.batch_size, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        ), dtype=np.float32)
        if result.shape != (len(texts), self.dimension) or not np.isfinite(result).all():
            raise ValueError("Embedding provider returned invalid dimensions or non-finite values")
        if np.any(np.linalg.norm(result, axis=1) < 1e-8):
            raise ValueError("Embedding provider returned a zero vector")
        return result.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed canonical property search sections (document role)."""
        return self._encode(texts, self.document_prefix)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed voice-agent runtime queries in the compatible query role."""
        return self._encode(texts, self.query_prefix)
