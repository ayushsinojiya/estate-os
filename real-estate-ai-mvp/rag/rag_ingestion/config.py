from pathlib import Path
import json
import os
from dataclasses import dataclass


@dataclass
class Settings:
    stores: dict[str, str]
    token: str
    storage_path: Path
    poll_seconds: float = 2
    embedding_model: str = ''
    embedding_revision: str = ''
    mistral_key: str = ''
    mistral_model: str = ''

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv(Path.cwd() / '.env', override=False)
        stores = json.loads(os.getenv('RAG_DATABASES_JSON', '{}'))
        if not stores or any(not str(k).isdigit() or int(k) <= 0 or not isinstance(v, str) or not v for k, v in stores.items()):
            raise ValueError('RAG_DATABASES_JSON must map existing positive CRM workspace IDs to dedicated PostgreSQL DSNs')
        if len(set(stores.values())) != len(stores):
            raise ValueError('Each workspace requires its own RAG database')
        token = os.getenv('RAG_INGESTION_TOKEN', '')
        if len(token) < 24:
            raise ValueError('RAG_INGESTION_TOKEN must contain at least 24 characters')
        return cls(stores, token, Path(os.getenv('RAG_STORAGE_PATH', './storage')).resolve(),
                   max(.2, float(os.getenv('RAG_POLL_SECONDS', '2'))),
                   os.getenv('RAG_EMBEDDING_MODEL', ''), os.getenv('RAG_EMBEDDING_REVISION', ''),
                   os.getenv('MISTRAL_API_KEY', ''), os.getenv('MISTRAL_EXTRACTION_MODEL', ''))

    def embedder(self):
        if not self.embedding_model or not self.embedding_revision:
            raise ValueError('Select a benchmarked embedding model and pinned revision before publishing')
        from .embeddings import SentenceTransformerProvider
        return SentenceTransformerProvider(self.embedding_model, self.embedding_revision)
