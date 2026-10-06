"""Provider construction from settings, shared by the API and the worker."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from rag_service.config import Settings
from rag_service.db import Database
from rag_service.providers.embeddings import Embedder, HashingEmbedder, OpenAIEmbedder
from rag_service.providers.llm import ChatJsonModel, JsonModel, MistralOCRParser, OpenAIJsonModel, OpenAIVisionParser, PageParser
from rag_service.storage import FileStore
from rag_service.store import Store


@dataclass
class Services:
    settings: Settings
    db: Database
    store: Store
    files: FileStore
    embedder: Embedder
    parser: PageParser | None
    json_model: JsonModel | None
    http: httpx.AsyncClient
    extraction_model: ChatJsonModel | None = None


def build_services(settings: Settings) -> Services:
    http = httpx.AsyncClient(limits=httpx.Limits(max_connections=50, max_keepalive_connections=20))
    db = Database(settings)
    live = settings.provider_mode == "live"
    if live and settings.openai_api_key:
        embedder: Embedder = OpenAIEmbedder(settings.openai_api_key, settings.embedding_model,
                                            settings.embedding_dim, settings.request_dimensions,
                                            settings.openai_base_url, settings.embedding_batch_size, http)
        json_model: JsonModel | None = OpenAIJsonModel(settings.openai_api_key, settings.classifier_model,
                                                       settings.openai_base_url, http)
    elif live:
        raise RuntimeError("PROVIDER_MODE=live needs OPENAI_API_KEY for embeddings (or set PROVIDER_MODE=fake)")
    else:
        embedder, json_model = HashingEmbedder(settings.embedding_dim), None

    parser: PageParser | None = None
    if live and settings.parser_provider == "mistral" and settings.mistral_api_key:
        parser = MistralOCRParser(settings.mistral_api_key, settings.mistral_ocr_model,
                                  settings.mistral_base_url, settings.parse_max_retries, http)
    elif live and settings.openai_api_key:
        parser = OpenAIVisionParser(settings.openai_api_key, settings.parser_model, settings.openai_base_url,
                                    settings.parse_max_retries, http)
    extraction = (ChatJsonModel(settings.groq_api_key, settings.extraction_model, settings.extraction_base_url, http)
                  if live and settings.groq_api_key else None)
    return Services(settings, db, Store(db, settings.low_confidence_threshold),
                    FileStore(settings.rag_storage_path), embedder, parser, json_model, http, extraction)
