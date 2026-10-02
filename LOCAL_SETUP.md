# EstraOS local Docker setup

Docker runs the EstraOS web UI, Spring Boot CRM API, and property-knowledge ingestion API/worker. PostgreSQL runs on your machine, not in Docker. The CRM and knowledge services use separate local databases; Docker volumes retain only app files and embedding models.

## Prerequisites

- Docker Desktop running, with Compose v2 (`docker compose version`)
- Internet access for the first image build and the knowledge worker's first embedding-model download
- Local PostgreSQL listening on port `5432`, with a CRM database and a separate knowledge database with the `vector` extension
- Ports `3000`, `8080`, and `8090` available on localhost

## One-command full stack

1. From this repository root, create your private settings file:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` and replace every `REPLACE_...` value. The minimum local values are:

   - `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` for the local CRM database
   - `POSTGRES_HOST=host.docker.internal` and the local PostgreSQL port
   - `JWT_SECRET` (at least 32 random characters)
   - `DEMO_PASSWORD` (at least 12 characters)
   - `RAG_INGESTION_TOKEN` (at least 32 random characters)
   - `RAG_DATABASES_JSON`, pointing to the separate local knowledge database through `host.docker.internal`; URL-encode its password

   The sample maps CRM workspace `1`. Replace it with the real workspace ID if needed. For an empty CRM database, leave `SPRING_FLYWAY_ENABLED=true`. An existing database with tables but no Flyway history needs schema review first; do not let Flyway run V1 over it. This checkout's existing `estate_os` database uses `SPRING_FLYWAY_ENABLED=false` in the private `.env` pending that reconciliation.

3. Start every local service:

   ```powershell
   docker compose up --build -d
   ```

4. Check readiness and open the UI:

   ```powershell
   docker compose ps
   docker compose logs -f api knowledge-api knowledge-worker
   ```

   - UI: `http://localhost:3000`
   - CRM health: `http://localhost:8080/actuator/health`
   - CRM Swagger: `http://localhost:8080/swagger-ui.html`
   - Knowledge API: `http://localhost:8090`

   On a newly migrated demo database, sign in with `admin@estraos.demo` and your private `DEMO_PASSWORD`. The existing local `estate_os` database still has the legacy `admin@estateos.demo` account until its schema/data migration is reconciled.

## Start one component

Each service folder has its own `compose.yaml` and `.env.example`. Copy the example to `.env`, fill in its `REPLACE_...` values, then run its compose command from that folder.

| Component | Command | Notes |
| --- | --- | --- |
| CRM API | `cd real-estate-ai-mvp/backend; docker compose up --build -d` | Uses local PostgreSQL through `host.docker.internal:5432`; API is on `http://localhost:8080`. |
| Web UI | `cd real-estate-ai-mvp/frontend; docker compose up --build -d` | Start the API first. Set `VITE_API_URL` to the browser-reachable API URL, normally `http://localhost:8080/api/v1`. |
| Knowledge API + worker | `cd real-estate-ai-mvp/rag; docker compose up --build -d` | Uses a separate local PostgreSQL database with pgvector. Keep the same `RAG_INGESTION_TOKEN` as CRM. The first worker run downloads the embedding model. |

## Stop, rebuild, and reset

```powershell
# Stop containers while preserving local databases, files, and models.
docker compose down

# Rebuild after source changes.
docker compose up --build -d

# Remove Docker-managed file/model volumes. Local PostgreSQL databases are NOT deleted.
docker compose down -v
```

## Credentials and external integrations

- `.env` is ignored by Git; commit only `.env.example` files.
- Never place passwords, tokens, or API keys in `VITE_*` variables because they are embedded in browser JavaScript.
- The default `INTEGRATIONS_MODE=mock` has no external provider dependency. Supply the optional service URLs and keys only when switching to a real integration mode.
- The voice-agent source is not included in this checkout; its URL/key remain optional external-integration settings.

## Troubleshooting

- `port is already allocated`: change the matching `*_PORT` value in `.env`, then restart the affected stack.
- A Compose error containing `Set ... in .env`: copy the relevant `.env.example` and replace the placeholder for that required setting.
- Knowledge service cannot connect to PostgreSQL: verify `host.docker.internal:5432` is reachable from Docker, the DSN password is URL encoded, and the local knowledge database has pgvector installed.
- Existing CRM schema without `flyway_schema_history`: do not enable Flyway until that schema has been compared with the current migrations. Disabling Flyway avoids startup DDL but does not fill missing tables or columns.
- Startup is slow only on the first knowledge-worker execution: it is downloading the pinned local embedding model into a named volume.
