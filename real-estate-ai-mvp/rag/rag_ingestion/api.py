import secrets
from uuid import UUID
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from .config import Settings
from .database import Database
from .storage import LocalStorage
from .service import Service, ActionError, MAX_BYTES


def create_app(settings=None):
    settings = settings or Settings.from_env()
    app = FastAPI(title='EstateOS Knowledge Ingestion', version='0.1.0')
    storage = LocalStorage(settings.storage_path)

    def authorized(authorization: str = Header(default='')):
        if not secrets.compare_digest(authorization, 'Bearer ' + settings.token):
            raise HTTPException(401, 'Trusted CRM credentials required')

    def service(workspace: int, actor: int = Header(alias='X-Actor-Id', gt=0), _=Depends(authorized)):
        dsn = settings.stores.get(str(workspace))
        if not dsn:
            raise HTTPException(404, 'No knowledge database is configured for this workspace')
        return Service(Database(dsn, str(workspace)), storage), actor

    @app.exception_handler(ActionError)
    async def action_error(request, error):
        return JSONResponse(status_code=error.status, content={'code': 'INGESTION_ACTION_REJECTED', 'message': str(error)})

    @app.exception_handler(Exception)
    async def infrastructure_error(request, error):
        # Connection errors contain DSNs in some clients. Keep internal details internal.
        return JSONResponse(status_code=503, content={'code': 'INGESTION_UNAVAILABLE', 'message': 'Knowledge service unavailable; check its database and storage configuration'})

    @app.get('/health', dependencies=[Depends(authorized)])
    def health():
        for workspace, dsn in settings.stores.items():
            with Database(dsn, workspace).connect() as c:
                row = c.execute('SELECT workspace_id FROM rag_store WHERE id=1').fetchone()
                if not row or str(row['workspace_id']) != workspace:
                    raise HTTPException(503, 'Knowledge database is not initialized correctly')
                c.execute("SELECT '[1,2]'::vector")
        return {'status': 'ok', 'workspaces': len(settings.stores)}

    @app.get('/v1/workspaces/{workspace}/sources')
    def sources(page: int = Query(0, ge=0), size: int = Query(20, ge=1, le=100), search: str = '', status: str = '', context=Depends(service)):
        svc, _ = context
        return svc.list_sources(page, size, search, status)

    @app.get('/v1/workspaces/{workspace}/sources/{source}')
    def detail(source: UUID, context=Depends(service)):
        return context[0].detail(source)

    def upload(files, context, replacement=None):
        # UploadFile spools multipart to disk; each file is independently bounded.
        # Process each batch in one Service call while capping total in-memory bytes.
        if len(files) > 20:
            raise ActionError('At most 20 files may be submitted per batch', 400)
        records = []
        total = 0
        for file in files:
            content = file.file.read(MAX_BYTES + 1)
            total += len(content)
            if total > 200 * 1024 * 1024:
                raise ActionError('Batch exceeds 200 MB; use smaller batches', 400)
            records.append((file.filename, content))
        return context[0].upload_batch(context[1], records, replacement)

    @app.post('/v1/workspaces/{workspace}/batches', status_code=202)
    def batch(files: list[UploadFile] = File(), context=Depends(service)):
        return upload(files, context)

    @app.post('/v1/workspaces/{workspace}/sources/{source}/replace', status_code=202)
    def replace(source: UUID, files: list[UploadFile] = File(), context=Depends(service)):
        return upload(files, context, source)

    @app.post('/v1/workspaces/{workspace}/sources/{source}/retry', status_code=202)
    def retry(source: UUID, context=Depends(service)):
        return context[0].retry(source, context[1])

    @app.delete('/v1/workspaces/{workspace}/sources/{source}', status_code=202)
    def delete(source: UUID, context=Depends(service)):
        return context[0].delete(source, context[1])

    return app
