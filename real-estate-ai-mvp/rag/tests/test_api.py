from pathlib import Path
from fastapi.testclient import TestClient
from rag_ingestion.config import Settings


def test_api_rejects_untrusted_actor_and_unknown_workspace_before_db_access(tmp_path):
    from rag_ingestion.api import create_app
    settings = Settings({'1': 'postgresql://invalid/database'}, 'a' * 32, tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    assert client.get('/v1/workspaces/1/sources').status_code == 401
    assert client.get('/v1/workspaces/1/sources', headers={'Authorization': 'Bearer ' + 'a'*32}).status_code == 422
    assert client.get('/v1/workspaces/2/sources', headers={'Authorization': 'Bearer ' + 'a'*32, 'X-Actor-Id': '7'}).status_code == 404


def test_storage_cannot_escape_root(tmp_path):
    import pytest
    from rag_ingestion.storage import LocalStorage
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).path('../outside.csv')


def test_vectors_reject_nonfinite_wrong_dimensions_and_zero():
    import pytest
    from rag_ingestion.worker import vector_literal
    for bad in ([0, 0], [float('nan'), 1], [1]):
        with pytest.raises(ValueError):
            vector_literal(bad, 2)
    assert vector_literal([1, .5], 2) == '[1.0,0.5]'
