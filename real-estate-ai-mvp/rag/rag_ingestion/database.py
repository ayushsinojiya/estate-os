from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

JSON = Jsonb
WORKER_LOCK = 54827191
ACTION_LOCK = 54827192


class Database:
    def __init__(self, dsn, workspace):
        self.dsn, self.workspace = dsn, str(workspace)

    @contextmanager
    def connect(self, autocommit=False):
        with psycopg.connect(self.dsn, row_factory=dict_row, autocommit=autocommit, connect_timeout=5) as conn:
            yield conn

    def migrate(self):
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)', (ACTION_LOCK,))
            c.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
            c.execute('INSERT INTO rag_store(id,workspace_id) VALUES (1,%s) ON CONFLICT DO NOTHING', (int(self.workspace),))
            actual = c.execute('SELECT workspace_id FROM rag_store WHERE id=1').fetchone()['workspace_id']
            if str(actual) != self.workspace:
                raise ValueError('RAG database is already bound to another workspace')


def event(c, actor, action, source=None, version=None, batch=None, job=None, details=None):
    c.execute('INSERT INTO rag_events(actor_id,action,source_id,version_id,batch_id,job_id,details) VALUES (%s,%s,%s,%s,%s,%s,%s)',
              (actor, action, source, version, batch, job, JSON(details or {})))
