"""Embedding providers. OpenAI in production; a deterministic hashing embedder offline.

The fake embedder is not a semantic model: it hashes word and character-trigram features into a
fixed-size vector, so cosine similarity tracks lexical overlap. That keeps tests and offline evals
deterministic and honest about what they measure.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
import numpy as np

from rag_service.providers.http import post_json


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    tokens: int


class Embedder(Protocol):
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> EmbeddingResult: ...


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, dim: int, request_dimensions: int | None,
                 base_url: str = "https://api.openai.com/v1", batch_size: int = 256,
                 client: httpx.AsyncClient | None = None):
        self.model = model
        self.dim = dim
        self.request_dimensions = request_dimensions
        self.batch_size = min(256, batch_size)
        self._url = base_url.rstrip("/") + "/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient()

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors: list[list[float]] = []
        tokens = 0
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            payload: dict = {"model": self.model, "input": batch}
            if self.request_dimensions:
                payload["dimensions"] = self.request_dimensions
            data = await post_json(self._client, self._url, headers=self._headers, payload=payload,
                                   retries=4, timeout_s=30)
            rows = sorted(data["data"], key=lambda row: row["index"])
            for row in rows:
                if len(row["embedding"]) != self.dim:
                    raise ValueError(f"{self.model} returned {len(row['embedding'])} dims, "
                                     f"index expects {self.dim}")
                vectors.append(row["embedding"])
            tokens += int((data.get("usage") or {}).get("total_tokens", 0))
        return EmbeddingResult(vectors, tokens)


_WORD = re.compile(r"[\wऀ-ॿ઀-૿]+", re.UNICODE)


def _features(text: str) -> list[str]:
    words = [w.lower() for w in _WORD.findall(text)]
    feats = [f"w:{w}" for w in words]
    for w in words:
        padded = f"#{w}#"
        feats += [f"c:{padded[i:i + 3]}" for i in range(max(1, len(padded) - 2))]
    return feats


class HashingEmbedder:
    def __init__(self, dim: int, model: str = "fake-hashing-v1"):
        self.model = model
        self.dim = dim

    def vector(self, text: str) -> list[float]:
        v = np.zeros(self.dim, dtype=np.float32)
        for feat in _features(text):
            digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            v[index] += sign * (2.0 if feat.startswith("w:") else 1.0)
        norm = float(np.linalg.norm(v))
        if norm == 0:
            v[0] = 1.0
            norm = 1.0
        return (v / norm).tolist()

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult([self.vector(t) for t in texts],
                               sum(math.ceil(len(t) / 4) for t in texts))
