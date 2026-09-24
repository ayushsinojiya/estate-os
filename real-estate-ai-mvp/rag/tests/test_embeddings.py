import sys
from types import SimpleNamespace

import numpy as np
import pytest

from rag_ingestion.embeddings import SentenceTransformerProvider


class StubModel:
    max_seq_length = 128

    def __init__(self, *args, **kwargs):
        self.calls = []

    def get_sentence_embedding_dimension(self):
        return 3

    def tokenizer(self, texts, **kwargs):
        return {"input_ids": [list(range(len(text.split()) + 2)) for text in texts]}

    def encode(self, texts, **kwargs):
        self.calls.append(texts)
        return np.tile([1.0, 0.0, 0.0], (len(texts), 1))


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=StubModel))
    return SentenceTransformerProvider("intfloat/multilingual-e5-small", "a" * 40)


def test_e5_preserves_query_passage_roles_and_original_text(provider):
    assert provider.embed(["અમદાવાદ 3 BHK"])[0] == [1, 0, 0]
    provider.embed_queries(["पुणे घर"])
    assert provider._model.calls == [["passage: અમદાવાદ 3 BHK"], ["query: पुणे घर"]]


def test_identity_contains_revision_dimension_and_contract(provider):
    assert '"revision":"' + "a" * 40 + '"' in provider.model_id
    assert '"dimension":3' in provider.model_id
    assert '"document_prefix":"passage: "' in provider.model_id


def test_mutable_revision_rejected():
    with pytest.raises(ValueError, match="immutable"):
        SentenceTransformerProvider("model", "main")


def test_empty_inputs_and_overlong_sections(provider):
    assert provider.embed([]) == []
    with pytest.raises(ValueError, match="non-empty"):
        provider.embed([" "])
    with pytest.raises(ValueError, match="exceeds model limit"):
        provider.embed(["word " * 129])


def test_provider_errors_are_never_replaced_by_fake_embeddings(provider, monkeypatch):
    monkeypatch.setattr(provider._model, "encode", lambda *args, **kwargs: np.asarray([[float("nan")]*3]))
    with pytest.raises(ValueError, match="non-finite"):
        provider.embed(["Shivalik Sky"])


def test_other_models_are_unprefixed_and_configuration_changes_identity(provider):
    other = SentenceTransformerProvider("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "b" * 40)
    other.embed(["Type A"])
    other.embed_queries(["Type A"])
    assert other._model.calls == [["Type A"], ["Type A"]]
    custom = SentenceTransformerProvider("intfloat/multilingual-e5-small", "a" * 40, query_prefix="search: ")
    assert custom.model_id != provider.model_id


def test_wrong_vector_dimension_fails(provider, monkeypatch):
    monkeypatch.setattr(provider._model, "encode", lambda *args, **kwargs: np.ones((1, 2)))
    with pytest.raises(ValueError, match="invalid dimensions"):
        provider.embed(["Type A"])
