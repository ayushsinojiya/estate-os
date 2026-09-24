"""One logical operation per database. Embedding succeeds before live publication."""
import math
import time
import uuid
from psycopg import sql
from .database import WORKER_LOCK, ACTION_LOCK, JSON, event
from .canonical import reconcile, resolve_entities, representations, AREA_FIELDS, NUMERIC_FIELDS
from .parsing import parse_file, extract_facts, ParsingError


def vector_literal(vector, dimension):
    values = [float(x) for x in vector]
    if len(values) != dimension or not all(math.isfinite(x) for x in values) or not any(values):
        raise ValueError('Embedding provider returned an invalid vector')
    return '[' + ','.join(str(x) for x in values) + ']'


class Worker:
    def __init__(self, db, storage, embedder_factory, interpreter=None):
        self.db, self.storage = db, storage
        self.embedder_factory, self.interpreter = embedder_factory, interpreter
        self._embedder = None

    def stage(self, job, stage, message, details=None):
        with self.db.connect() as c:
            c.execute('UPDATE rag_jobs SET stage=%s WHERE id=%s', (stage, job['id']))
            c.execute('INSERT INTO rag_logs(job_id,stage,message,details) VALUES (%s,%s,%s,%s)', (job['id'], stage, message, JSON(details or {})))

    def fail(self, job, reason, retryable=True):
        with self.db.connect() as c:
            changed = c.execute("UPDATE rag_jobs SET status='FAILED',error=%s,retryable=%s,finished_at=now(),duration_ms=extract(epoch FROM(now()-started_at))*1000 WHERE id=%s AND status='PROCESSING' RETURNING id", (reason, retryable, job['id'])).fetchone()
            if not changed:
                return  # Commit may have succeeded before a connection error was reported.
            if job['source_id']:
                c.execute("UPDATE rag_sources SET status='FAILED' WHERE id=%s", (job['source_id'],))
            if job['kind'] == 'INGEST':
                c.execute("UPDATE rag_source_versions SET status='FAILED' WHERE id=%s AND status<>'ACTIVE'", (job['version_id'],))
            event(c, job['created_by'], 'JOB_FAILED', job['source_id'], job['version_id'], job=job['id'], details={'reason': reason, 'retryable': retryable})
            c.execute('INSERT INTO rag_logs(job_id,stage,message) VALUES (%s,%s,%s)', (job['id'], 'FAILED', reason))

    def run_once(self):
        with self.db.connect(autocommit=True) as lock:
            if not lock.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (WORKER_LOCK,)).fetchone()['acquired']:
                return False
            try:
                # The session lock cannot be obtained while a living worker owns this DB.
                for abandoned in lock.execute("SELECT * FROM rag_jobs WHERE status='PROCESSING'").fetchall():
                    self.fail(abandoned, 'Worker interrupted. Published knowledge is unchanged; use Retry.')
                self.cleanup()
                with lock.transaction():
                    job = lock.execute("SELECT * FROM rag_jobs WHERE status='QUEUED' ORDER BY created_at,id LIMIT 1 FOR UPDATE").fetchone()
                    if not job:
                        return False
                    lock.execute("UPDATE rag_jobs SET status='PROCESSING',started_at=now() WHERE id=%s", (job['id'],))
                    if job['source_id']:
                        lock.execute("UPDATE rag_sources SET status='PROCESSING' WHERE id=%s", (job['source_id'],))
                    if job['kind'] == 'INGEST':
                        lock.execute("UPDATE rag_source_versions SET status='PROCESSING' WHERE id=%s", (job['version_id'],))
                    event(lock, job['created_by'], 'JOB_STARTED', job['source_id'], job['version_id'], job=job['id'], details={'kind': job['kind']})
                try:
                    if job['kind'] == 'REEMBED':
                        self.reembed(lock, job)
                    else:
                        self.process(lock, job)
                except Exception as exc:
                    # Do not expose provider payloads, DSNs, or source document contents.
                    reason = str(exc)[:500] if isinstance(exc, (ParsingError, ValueError)) else f'{type(exc).__name__} during ingestion; check service configuration and use Retry'
                    self.fail(job, reason, getattr(exc, 'retryable', True))
                self.cleanup()
                return True
            finally:
                lock.execute('SELECT pg_advisory_unlock(%s)', (WORKER_LOCK,))

    def contributions(self):
        with self.db.connect() as c:
            rows = c.execute('''SELECT x.*,v.source_id,v.filename,v.publication_order FROM rag_contributions x
                JOIN rag_source_versions v ON v.id=x.version_id JOIN rag_sources s ON s.active_version=v.id''').fetchall()
        for row in rows:
            for key in ('entity_id', 'parent_id', 'source_id', 'version_id'):
                if row[key] is not None:
                    row[key] = str(row[key])
        return rows

    def model(self):
        if self._embedder is None:
            self._embedder = self.embedder_factory()
        return self._embedder

    def process(self, lock, job):
        old = self.contributions()
        source = str(job['source_id'])
        remaining = [r for r in old if r['source_id'] != source]
        new_rows = []
        sequence = lock.execute('SELECT publication_sequence FROM rag_store WHERE id=1').fetchone()['publication_sequence'] + 1
        if job['kind'] == 'INGEST':
            version = lock.execute('SELECT * FROM rag_source_versions WHERE id=%s', (job['version_id'],)).fetchone()
            self.stage(job, 'EXTRACTING', 'Reading native content; local OCR is used for scanned pages and embedded images')
            raw = parse_file(self.storage.path(version['storage_key']), version['filename'])
            with self.db.connect() as c:
                c.execute('UPDATE rag_source_versions SET raw_extraction=%s WHERE id=%s', (JSON(raw), version['id']))
            self.stage(job, 'INTERPRETING', 'Extracting explicit facts with source provenance')
            extracted = extract_facts(raw, self.interpreter)
            with self.db.connect() as c:
                c.execute('UPDATE rag_source_versions SET extracted_entities=%s,warnings=%s WHERE id=%s', (JSON(extracted['entities']), JSON(extracted['warnings']), version['id']))
            resolved = resolve_entities(extracted['entities'], source, old)
            by_id = {}
            for row in resolved:
                eid = row['entity_id']
                if eid in by_id:
                    previous = by_id[eid]
                    for field, fact in row['facts'].items():
                        if field in previous['facts'] and previous['facts'][field]['value'] != fact['value']:
                            raise ValueError('Conflicting facts for the same entity within this file; correct the source and replace it')
                    previous['facts'].update(row['facts'])
                else:
                    by_id[eid] = dict(row, version_id=str(version['id']), publication_order=sequence, filename=version['filename'])
            new_rows = list(by_id.values())
        self.stage(job, 'RECONCILING', 'Computing per-field winners from active sources')
        before, after = reconcile(old), reconcile(remaining + new_rows)
        old_sections = {eid: representations(e, before) for eid, e in before.items()}
        new_sections = {eid: representations(e, after) for eid, e in after.items()}
        changed = {eid for eid in set(before) | set(after) if before.get(eid) != after.get(eid) or old_sections.get(eid) != new_sections.get(eid)}
        sections = [r for eid in sorted(changed) for r in new_sections.get(eid, [])]
        active = lock.execute('SELECT s.* FROM rag_embedding_sets s JOIN rag_store r ON r.active_embedding_set=s.id').fetchone()
        model = self.model() if sections else None
        if model and active and (model.model_id != active['model_id'] or model.dimension != active['dimensions']):
            raise ValueError('Embedding model differs from live knowledge. Run the full reembed command before ingestion.')
        self.stage(job, 'EMBEDDING', 'Preparing vectors before publication', {'sections': len(sections), 'affectedEntities': len(changed)})
        vectors = model.embed([r['content'] for r in sections]) if sections else []
        if len(vectors) != len(sections):
            raise ValueError('Embedding provider returned the wrong number of vectors')
        literals = [vector_literal(v, model.dimension) for v in vectors]
        set_id = active['id'] if active else uuid.uuid4() if sections else None
        self.stage(job, 'PUBLISHING', 'Atomically publishing canonical entities, keywords and vectors')
        # Use the SAME connection that owns WORKER_LOCK for the publication transaction.
        with lock.transaction():
            lock.execute('SELECT pg_advisory_xact_lock(%s)', (ACTION_LOCK,))
            if not active and sections:
                lock.execute("INSERT INTO rag_embedding_sets(id,model_id,dimensions,status) VALUES (%s,%s,%s,'LIVE')", (set_id, model.model_id, model.dimension))
                lock.execute('UPDATE rag_store SET active_embedding_set=%s WHERE id=1', (set_id,))
            self.retire_versions(lock, job, keep=job['version_id'] if job['kind'] == 'INGEST' else None)
            if job['kind'] == 'INGEST':
                for row in new_rows:
                    lock.execute('INSERT INTO rag_contributions(version_id,entity_id,kind,parent_id,identity,facts) VALUES (%s,%s,%s,%s,%s,%s)',
                                 (job['version_id'], row['entity_id'], row['kind'], row['parent_id'], JSON(row['identity']), JSON(row['facts'])))
                lock.execute("UPDATE rag_source_versions SET status='ACTIVE',published_at=now(),publication_order=%s WHERE id=%s", (sequence, job['version_id']))
                lock.execute("UPDATE rag_sources SET active_version=%s,status='ACTIVE' WHERE id=%s", (job['version_id'], job['source_id']))
            else:
                lock.execute("UPDATE rag_sources SET active_version=NULL,status='DELETED',deleted_at=now() WHERE id=%s", (job['source_id'],))
            for eid in changed:
                lock.execute('DELETE FROM rag_search_records WHERE embedding_set_id=%s AND entity_id=%s', (set_id, eid))
                lock.execute('DELETE FROM rag_entities WHERE id=%s', (eid,))
                if eid in after:
                    self.insert_entity(lock, after[eid])
            for section, vector in zip(sections, literals):
                self.insert_section(lock, set_id, section, vector, after)
            lock.execute('UPDATE rag_store SET publication_sequence=%s WHERE id=1', (sequence,))
            self.complete(lock, job, {'affectedEntities': len(changed), 'sections': len(sections)})

    def retire_versions(self, c, job, keep=None):
        versions = c.execute('SELECT id,storage_key,status FROM rag_source_versions WHERE source_id=%s AND (%s::uuid IS NULL OR id<>%s::uuid)', (job['source_id'], keep, keep)).fetchall()
        for version in versions:
            if version['storage_key']:
                c.execute('INSERT INTO rag_file_cleanup(storage_key,source_id,version_id,actor_id) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING', (version['storage_key'], job['source_id'], version['id'], job['created_by']))
            c.execute('DELETE FROM rag_contributions WHERE version_id=%s', (version['id'],))
            c.execute("UPDATE rag_source_versions SET status=%s,raw_extraction=NULL,extracted_entities=NULL WHERE id=%s", ('RETIRED' if keep else 'DELETED', version['id']))
            if version['status'] != ('RETIRED' if keep else 'DELETED'):
                event(c, job['created_by'], 'SOURCE_VERSION_RETIRED' if keep else 'SOURCE_VERSION_DELETED',
                      job['source_id'], version['id'], job=job['id'], details={'previousStatus': version['status']})

    @staticmethod
    def complete(c, job, details):
        c.execute("UPDATE rag_jobs SET status='SUCCEEDED',stage='COMPLETE',finished_at=now(),duration_ms=extract(epoch FROM(now()-started_at))*1000 WHERE id=%s", (job['id'],))
        event(c, job['created_by'], job['kind'] + '_PUBLISHED', job['source_id'], job['version_id'], job=job['id'], details=details)
        c.execute("INSERT INTO rag_logs(job_id,stage,message,details) VALUES (%s,'COMPLETE','Publication committed',%s)", (job['id'], JSON(details)))

    @staticmethod
    def insert_entity(c, entity):
        values = {'id': entity['id'], 'kind': entity['kind'], 'parent_id': entity['parent_id'], 'canonical': JSON(entity)}
        text_fields = ('name project_name configuration_name property_type property_subtype availability_status status country state city locality address currency possession_status possession_date facing furnishing_status developer_name rera_id').split()
        for field in text_fields:
            value = entity['facts'].get(field)
            if isinstance(value, (str, int, float)):
                values[field] = str(value)
        for field in NUMERIC_FIELDS:
            if field in entity['facts']:
                values[field] = entity['facts'][field]
        for field in AREA_FIELDS:
            values[field + '_sqft'] = entity['facts'].get(field, {}).get('sqft')
        if 'parking' in entity['facts']:
            values['parking'] = JSON(entity['facts']['parking'])
        c.execute(sql.SQL('INSERT INTO rag_entities ({}) VALUES ({})').format(sql.SQL(',').join(map(sql.Identifier, values)), sql.SQL(',').join(sql.Placeholder() for _ in values)), tuple(values.values()))

    @staticmethod
    def insert_section(c, set_id, row, vector, entities):
        ancestors = [entities[eid] for eid in row['metadata']['parent_context_ids'] if eid in entities]
        values = {'id': uuid.uuid4(), 'embedding_set_id': set_id, 'entity_id': row['entity_id'], 'entity_type': row['entity_type'],
                  'project_id': next((e['id'] for e in ancestors if e['kind'] == 'PROJECT'), row['entity_id'] if row['entity_type'] == 'PROJECT' else None),
                  'configuration_id': next((e['id'] for e in ancestors if e['kind'] == 'CONFIGURATION'), row['entity_id'] if row['entity_type'] == 'CONFIGURATION' else None),
                  'section_type': row['section_type'], 'content': row['content'], 'embedding': vector, 'priority': row['priority'],
                  **row['filters'], 'metadata': JSON(row['metadata']), 'provenance': JSON(row['provenance'])}
        for field in AREA_FIELDS:
            values[field + '_sqft'] = row['metadata']['areas'].get(field, {}).get('sqft')
        placeholders = [sql.SQL('%s::vector') if k == 'embedding' else sql.Placeholder() for k in values]
        c.execute(sql.SQL('INSERT INTO rag_search_records ({}) VALUES ({})').format(sql.SQL(',').join(map(sql.Identifier, values)), sql.SQL(',').join(placeholders)), tuple(values.values()))

    def reembed(self, lock, job):
        from .embeddings import SentenceTransformerProvider
        model = SentenceTransformerProvider(job['options']['model'], job['options']['revision'])
        entities = reconcile(self.contributions())
        sections = [r for e in entities.values() for r in representations(e, entities)]
        self.stage(job, 'EMBEDDING', 'Building a complete replacement embedding set', {'sections': len(sections)})
        vectors = model.embed([r['content'] for r in sections]) if sections else []
        if len(vectors) != len(sections):
            raise ValueError('Embedding provider returned the wrong number of vectors')
        literals = [vector_literal(v, model.dimension) for v in vectors]
        set_id = uuid.uuid4()
        with lock.transaction():
            lock.execute('SELECT pg_advisory_xact_lock(%s)', (ACTION_LOCK,))
            lock.execute("INSERT INTO rag_embedding_sets(id,model_id,dimensions,status) VALUES (%s,%s,%s,'STAGING')", (set_id, model.model_id, model.dimension))
            for row, vector in zip(sections, literals):
                self.insert_section(lock, set_id, row, vector, entities)
            lock.execute("UPDATE rag_embedding_sets SET status='RETIRED' WHERE status='LIVE'")
            lock.execute("UPDATE rag_embedding_sets SET status='LIVE' WHERE id=%s", (set_id,))
            lock.execute('UPDATE rag_store SET active_embedding_set=%s WHERE id=1', (set_id,))
            lock.execute('DELETE FROM rag_search_records WHERE embedding_set_id<>%s', (set_id,))
            self.complete(lock, job, {'sections': len(sections), 'modelId': model.model_id})
        self._embedder = model

    def cleanup(self):
        with self.db.connect() as c:
            pending = c.execute('SELECT * FROM rag_file_cleanup').fetchall()
        for row in pending:
            try:
                self.storage.delete(row['storage_key'])
                with self.db.connect() as c:
                    c.execute('UPDATE rag_source_versions SET storage_key=NULL WHERE id=%s AND storage_key=%s', (row['version_id'], row['storage_key']))
                    c.execute('DELETE FROM rag_file_cleanup WHERE storage_key=%s', (row['storage_key'],))
                    event(c, row['actor_id'], 'RETIRED_FILE_REMOVED', row['source_id'], row['version_id'])
            except OSError:
                with self.db.connect() as c:
                    c.execute("UPDATE rag_file_cleanup SET last_error='Filesystem cleanup failed; will retry separately from ingestion' WHERE storage_key=%s", (row['storage_key'],))
