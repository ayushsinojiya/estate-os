"""Use a disposable database: tests create a private schema, never drop a database."""
import os
import uuid
import pytest
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg import sql


@pytest.fixture
def stack(tmp_path):
    dsn = os.getenv('RAG_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set RAG_TEST_DATABASE_URL to an isolated pgvector database')
    from rag_ingestion.database import Database
    from rag_ingestion.storage import LocalStorage
    from rag_ingestion.service import Service
    from rag_ingestion.worker import Worker
    schema = 'test_' + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute('CREATE EXTENSION IF NOT EXISTS vector')
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    db = Database(make_conninfo(dsn, options=f'-c search_path={schema},public'), '1')
    db.migrate()
    storage = LocalStorage(tmp_path)
    # Deterministic test double ONLY; production has no fake vector fallback.
    class Embedder:
        model_id, dimension, fail = 'test-only-v1', 3, False
        def embed(self, texts):
            if self.fail:
                raise RuntimeError('injected embedding outage')
            return [[1., .2, .3] for _ in texts]
    model = Embedder()
    try:
        yield Service(db, storage), Worker(db, storage, lambda: model), model, db
    finally:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def upload(service, price, replacement=None):
    data = f'property_id,city,bhk,price,balconies\nP1,Pune,2,{price},1\n'.encode()
    return service.upload_batch(7, [('price.csv', data)], replacement)['results'][0]['id']


def facts(db):
    with db.connect() as c:
        return c.execute('SELECT canonical FROM rag_entities').fetchone()['canonical']['facts']


def test_failed_replacement_keeps_live_version_then_manual_retry_publishes(stack):
    service, worker, model, db = stack
    source = upload(service, '85 lakh')
    assert worker.run_once()
    original = service.detail(source)['source']['activeVersion']
    model.fail = True
    upload(service, '90 lakh', source)
    worker.run_once()
    assert facts(db)['price_min'] == 8500000
    assert service.detail(source)['source']['activeVersion'] == original
    assert service.detail(source)['source']['status'] == 'FAILED'
    assert not worker.run_once()  # Never automatically retry.
    model.fail = False
    service.retry(source, 7)
    worker.run_once()
    assert facts(db)['price_min'] == 9000000
    assert service.detail(source)['source']['activeVersion'] != original
    actions = {event['action'] for event in service.detail(source)['events']}
    assert {'JOB_STARTED', 'SOURCE_REPLACEMENT_QUEUED', 'RETRY_REQUESTED', 'SOURCE_VERSION_RETIRED'} <= actions


def test_delete_reconstructs_older_facts_and_removes_files(stack):
    service, worker, model, db = stack
    first = upload(service, '85 lakh')
    worker.run_once()
    second = upload(service, '90 lakh')
    worker.run_once()
    assert facts(db)['price_min'] == 9000000
    service.delete(second, 7)
    worker.run_once()
    assert facts(db)['price_min'] == 8500000
    assert service.detail(second)['source']['status'] == 'DELETED'
    service.delete(first, 7)
    worker.run_once()
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM rag_live_knowledge').fetchone()['n'] == 0
        assert c.execute('SELECT count(*) AS n FROM rag_file_cleanup').fetchone()['n'] == 0


def test_duplicate_is_skipped_without_creating_another_source(stack):
    service, worker, model, db = stack
    source = upload(service, '85 lakh')
    result = service.upload_batch(7, [('same.csv', b'property_id,city,bhk,price,balconies\nP1,Pune,2,85 lakh,1\n')])
    assert result['results'][0]['status'] == 'DUPLICATE'
    assert result['results'][0]['id'] == source
    assert service.list_sources()['total'] == 1


def test_worker_lock_and_interrupted_job_require_manual_retry(stack):
    from rag_ingestion.database import WORKER_LOCK
    service, worker, model, db = stack
    source = upload(service, '85 lakh')
    with db.connect(autocommit=True) as c:
        c.execute('SELECT pg_advisory_lock(%s)', (WORKER_LOCK,))
        assert not worker.run_once()
    with db.connect() as c:
        c.execute("UPDATE rag_jobs SET status='PROCESSING',started_at=now()")
    assert not worker.run_once()
    assert service.detail(source)['source']['status'] == 'FAILED'
    service.retry(source, 7)
    worker.run_once()
    assert facts(db)['city'] == 'Pune'


def test_partial_batch_accepts_good_file_and_rejects_unsupported(stack):
    service, worker, model, db = stack
    result = service.upload_batch(7, [('bad.zip', b'zip'), ('good.csv', b'property_id,city\nP1,Pune\n')])
    assert [r['status'] for r in result['results']] == ['REJECTED', 'QUEUED']
    worker.run_once()
    assert facts(db)['city'] == 'Pune'


def test_delete_unpublished_source_never_loads_embedding_model(stack):
    service, worker, model, db = stack
    source = service.upload_batch(7, [('bad.csv', b'nonsense\ncontent\n')])['results'][0]['id']
    worker.run_once()
    def unavailable():
        pytest.fail('Deleting an unpublished source must not load a model')
    worker.embedder_factory = unavailable
    service.delete(source, 7)
    worker.run_once()
    assert service.detail(source)['source']['status'] == 'DELETED'


def test_reembedding_is_atomic_and_preserves_old_set_on_model_failure(stack, monkeypatch):
    service, worker, model, db = stack
    source = upload(service, '85 lakh')
    worker.run_once()
    def live():
        with db.connect() as c:
            return c.execute('SELECT DISTINCT model_id FROM rag_live_knowledge').fetchall()
    class NewModel:
        model_id, dimension, fail = 'test-only-v2', 4, True
        def embed(self, texts):
            assert live() == [{'model_id': 'test-only-v1'}]
            if self.fail:
                raise RuntimeError('test outage')
            return [[1., 2., 3., 4.] for _ in texts]
    replacement = NewModel()
    monkeypatch.setattr('rag_ingestion.embeddings.SentenceTransformerProvider', lambda *args: replacement)
    service.reembed(7, 'test-only', 'a'*40)
    worker.run_once()
    assert live() == [{'model_id': 'test-only-v1'}]
    replacement.fail = False
    service.reembed(7, 'test-only', 'a'*40)
    worker.run_once()
    assert live() == [{'model_id': 'test-only-v2'}]
    assert service.detail(source)['source']['status'] == 'ACTIVE'


def test_mixed_property_fixture_populates_generic_typed_and_dynamic_fields(stack):
    from pathlib import Path
    service, worker, model, db = stack
    data = Path('examples/mixed-property-types.csv').read_bytes()
    service.upload_batch(7, [('mixed.csv', data)])
    worker.run_once()
    with db.connect() as c:
        rows = c.execute('SELECT property_type,bhk,property_subtype,availability_status,canonical FROM rag_entities').fetchall()
        assert len(rows) == 5
        office = next(row for row in rows if row['property_type'] == 'Office')
        assert office['bhk'] is None
        assert office['canonical']['facts']['workstations'] == '40'
        assert office['property_subtype'] == 'Commercial'
        assert office['availability_status'] == 'Available'


def test_replacement_reusing_ai_key_does_not_transfer_another_propertys_facts(stack):
    service, worker, model, db = stack
    def interpret(raw):
        text = raw['blocks'][0]['text']
        values = {'property_id': 'P1', 'city': 'Pune'} if 'P1' in text else {'property_id': 'P2', 'city': 'Mumbai'}
        return {'entities': [{'key': 'property_1', 'kind': 'PROPERTY', 'identity': values,
                             'facts': {field: {'value': value, 'evidence': {
                                 'quote': text, 'locator': {'block': 1, 'format': 'txt'}}}
                                       for field, value in values.items()}}]}
    worker.interpreter = interpret
    source = service.upload_batch(7, [('listing.txt', b'Listing P1 is located in Pune.')])['results'][0]['id']
    worker.run_once()
    service.upload_batch(7, [('details.csv', b'property_id,balconies\nP1,2\n')])
    worker.run_once()
    service.upload_batch(7, [('replacement.txt', b'Listing P2 is located in Mumbai.')], source)
    worker.run_once()
    assert service.detail(source)['source']['status'] == 'ACTIVE'
    with db.connect() as c:
        rows = c.execute('SELECT canonical FROM rag_entities').fetchall()
    by_property = {r['canonical']['facts']['property_id']: r['canonical']['facts'] for r in rows}
    assert set(by_property) == {'P1', 'P2'}
    assert by_property['P1']['balconies'] == 2
    assert by_property['P2']['city'] == 'Mumbai'
    assert 'balconies' not in by_property['P2']
