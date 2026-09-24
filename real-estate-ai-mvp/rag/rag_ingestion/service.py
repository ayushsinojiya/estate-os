"""Durable user actions. Parsing and model calls never run in request transactions."""
import hashlib
import uuid
from pathlib import PurePosixPath
from .database import ACTION_LOCK, JSON, event

SUPPORTED = {'pdf', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'md'}
MAX_BYTES = 50 * 1024 * 1024


class ActionError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class Service:
    def __init__(self, db, storage):
        self.db, self.storage = db, storage

    def _lock(self, c):
        c.execute('SELECT pg_advisory_xact_lock(%s)', (ACTION_LOCK,))

    def _source(self, c, source):
        row = c.execute('SELECT * FROM rag_sources WHERE id=%s', (source,)).fetchone()
        if not row:
            raise ActionError('Source not found', 404)
        if row['status'] == 'DELETED':
            raise ActionError('Source has been deleted')
        if c.execute("SELECT 1 FROM rag_jobs WHERE source_id=%s AND status IN ('QUEUED','PROCESSING')", (source,)).fetchone():
            raise ActionError('This source already has a pending operation')
        return row

    def _job(self, c, actor, source, version, kind, options=None):
        job = str(uuid.uuid4())
        c.execute('INSERT INTO rag_jobs(id,source_id,version_id,kind,status,stage,created_by,options) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                  (job, source, version, kind, 'QUEUED', kind, actor, JSON(options or {})))
        if source:
            c.execute("UPDATE rag_sources SET status='QUEUED' WHERE id=%s", (source,))
        event(c, actor, kind + '_QUEUED', source, version, job=job)
        return {'jobId': job, 'status': 'QUEUED'}

    def upload_batch(self, actor, files, replacement=None):
        if replacement and len(files) != 1:
            raise ActionError('Replacement requires exactly one file', 400)
        if not files:
            raise ActionError('Choose at least one file', 400)
        batch = str(uuid.uuid4())
        with self.db.connect() as c:
            c.execute('INSERT INTO rag_batches(id,created_by) VALUES (%s,%s)', (batch, actor))
        results = []
        for filename, content in files:
            key = None
            filename = PurePosixPath((filename or 'file').replace('\\', '/')).name[:255]
            extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            try:
                if extension not in SUPPORTED:
                    raise ActionError('Unsupported knowledge file; use PDF, DOCX, XLS/XLSX, CSV, TXT or Markdown', 400)
                if not content or len(content) > MAX_BYTES:
                    raise ActionError('File must be nonempty and at most 50 MB', 400)
                checksum = hashlib.sha256(content).hexdigest()
                with self.db.connect() as c:
                    self._lock(c)
                    if replacement:
                        self._source(c, replacement)
                    duplicate = c.execute("SELECT source_id FROM rag_source_versions WHERE sha256=%s AND status IN ('QUEUED','PROCESSING','ACTIVE')", (checksum,)).fetchone()
                    if duplicate:
                        event(c, actor, 'DUPLICATE_SKIPPED', duplicate['source_id'], batch=batch, details={'filename': filename})
                        results.append({'id': str(duplicate['source_id']), 'filename': filename, 'status': 'DUPLICATE', 'reason': 'Identical content is already active or queued'})
                        continue
                    source, version = replacement or str(uuid.uuid4()), str(uuid.uuid4())
                    if not replacement:
                        c.execute("INSERT INTO rag_sources(id,status,created_by) VALUES (%s,'QUEUED',%s)", (source, actor))
                    n = c.execute('SELECT coalesce(max(version),0)+1 AS n FROM rag_source_versions WHERE source_id=%s', (source,)).fetchone()['n']
                    key = self.storage.save(self.db.workspace, version, content, extension)
                    c.execute("INSERT INTO rag_source_versions(id,source_id,batch_id,version,filename,extension,size_bytes,sha256,storage_key,status,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s)",
                              (version, source, batch, n, filename, extension, len(content), checksum, key, actor))
                    queued = self._job(c, actor, source, version, 'INGEST')
                    if replacement:
                        event(c, actor, 'SOURCE_REPLACEMENT_QUEUED', source, version, batch, queued['jobId'])
                    event(c, actor, 'FILE_RECEIVED', source, version, batch, details={'filename': filename, 'sha256': checksum, 'bytes': len(content)})
                key = None
                results.append({'id': str(source), 'filename': filename, 'status': 'QUEUED'})
            except ActionError as exc:
                with self.db.connect() as c:
                    event(c, actor, 'UPLOAD_REJECTED', batch=batch, details={'filename': filename, 'reason': str(exc)})
                results.append({'id': replacement, 'filename': filename, 'status': 'REJECTED', 'reason': str(exc)})
            finally:
                if key:
                    self.storage.delete(key)
        return {'batchId': batch, 'results': results}

    def retry(self, source, actor):
        with self.db.connect() as c:
            self._lock(c)
            self._source(c, source)
            job = c.execute('SELECT * FROM rag_jobs WHERE source_id=%s ORDER BY created_at DESC,id DESC LIMIT 1', (source,)).fetchone()
            if not job or job['status'] != 'FAILED' or not job['retryable']:
                raise ActionError('No retryable failed operation exists for this source')
            if job['kind'] == 'INGEST':
                version = c.execute('SELECT * FROM rag_source_versions WHERE id=%s', (job['version_id'],)).fetchone()
                if not version['storage_key'] or not self.storage.path(version['storage_key']).is_file():
                    raise ActionError('Original file is unavailable; replace the source with a new upload')
                if c.execute("SELECT 1 FROM rag_source_versions WHERE sha256=%s AND id<>%s AND status IN ('QUEUED','PROCESSING','ACTIVE')", (version['sha256'], version['id'])).fetchone():
                    raise ActionError('Identical content is already active or queued')
                c.execute("UPDATE rag_source_versions SET status='QUEUED' WHERE id=%s", (version['id'],))
            queued = self._job(c, actor, source, job['version_id'], job['kind'], job['options'])
            event(c, actor, 'RETRY_REQUESTED', source, job['version_id'], job=queued['jobId'], details={'previousJobId': str(job['id'])})
            return queued

    def delete(self, source, actor):
        with self.db.connect() as c:
            self._lock(c)
            row = self._source(c, source)
            return self._job(c, actor, source, row['active_version'], 'DELETE')

    def reembed(self, actor, model, revision):
        if not model or not revision:
            raise ActionError('Model and immutable revision are required', 400)
        with self.db.connect() as c:
            self._lock(c)
            if c.execute("SELECT 1 FROM rag_jobs WHERE kind='REEMBED' AND status IN ('QUEUED','PROCESSING')").fetchone():
                raise ActionError('A full re-embedding job is already pending')
            return self._job(c, actor, None, None, 'REEMBED', {'model': model, 'revision': revision})

    def list_sources(self, page=0, size=20, search='', status=''):
        page, size = max(0, page), max(1, min(size, 100))
        with self.db.connect() as c:
            # Latest attempted version is visible while activeVersion identifies the live one.
            query = '''FROM rag_sources s
              JOIN LATERAL (SELECT * FROM rag_source_versions WHERE source_id=s.id ORDER BY version DESC LIMIT 1) v ON true
              LEFT JOIN rag_source_versions live ON live.id=s.active_version
              LEFT JOIN LATERAL (SELECT * FROM rag_jobs WHERE source_id=s.id ORDER BY created_at DESC,id DESC LIMIT 1) j ON true
              WHERE (%s='' OR v.filename ILIKE %s) AND (%s='' OR s.status=%s)'''
            params = (search, '%' + search.replace('%', '\\%').replace('_', '\\_') + '%', status, status)
            total = c.execute('SELECT count(*) AS n ' + query, params).fetchone()['n']
            rows = c.execute('''SELECT s.id,s.status,s.active_version,s.created_at,v.filename,v.extension,v.size_bytes,v.batch_id,v.version,
                                live.version AS active_version_number,j.stage,j.error,j.retryable ''' + query + ' ORDER BY s.created_at DESC,s.id DESC LIMIT %s OFFSET %s', (*params, size, page * size)).fetchall()
        return {'items': [self._public(row) for row in rows], 'total': total, 'page': page, 'size': size}

    @staticmethod
    def _public(row):
        mapping = {'filename': 'originalFileName', 'extension': 'fileExtension', 'size_bytes': 'fileSizeBytes',
                   'active_version': 'activeVersion', 'active_version_number': 'activeVersionNumber', 'created_at': 'createdAt', 'batch_id': 'batchId', 'error': 'failureReason'}
        return {mapping.get(k, k): str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()}

    def detail(self, source):
        with self.db.connect() as c:
            s = c.execute('SELECT * FROM rag_sources WHERE id=%s', (source,)).fetchone()
            if not s:
                raise ActionError('Source not found', 404)
            versions = c.execute('SELECT id,version,filename,extension,size_bytes,status,warnings,created_at,published_at FROM rag_source_versions WHERE source_id=%s ORDER BY version DESC', (source,)).fetchall()
            jobs = c.execute('SELECT id,kind,status,stage,error,retryable,created_by,created_at,started_at,finished_at,duration_ms FROM rag_jobs WHERE source_id=%s ORDER BY created_at DESC,id DESC', (source,)).fetchall()
            events = c.execute('SELECT * FROM rag_events WHERE source_id=%s ORDER BY id DESC LIMIT 200', (source,)).fetchall()
            logs = c.execute('SELECT l.* FROM rag_logs l JOIN rag_jobs j ON j.id=l.job_id WHERE j.source_id=%s ORDER BY l.id DESC LIMIT 300', (source,)).fetchall()
            latest = versions[0] if versions else {}
            info = dict(s, filename=latest.get('filename'), extension=latest.get('extension'), size_bytes=latest.get('size_bytes'), version=latest.get('version'), stage=jobs[0]['stage'] if jobs else None, error=jobs[0]['error'] if jobs else None)
            info['active_version_number'] = next((v['version'] for v in versions if v['id'] == s['active_version']), None)
        return {'source': self._public(info), 'versions': versions, 'jobs': jobs, 'events': events, 'logs': logs}
