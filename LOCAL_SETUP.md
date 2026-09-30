# EstraOS local Docker setup

This repository runs three local services: the EstraOS web UI, the Spring Boot CRM API with PostgreSQL, and the property-knowledge ingestion API/worker with a separate pgvector database. Docker named volumes keep data between restarts.

## Prerequisites

- Docker Desktop running, with Compose v2 (`docker compose version`)
- Internet access for the first image build and the knowledge worker's first embedding-model download
- Ports `3000`, `8080`, `8090`, and `55432` available on localhost

## One-command full stack

1. From this repository root, create your private settings file:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` and replace every `REPLACE_...` value. The minimum local values are:

   - `POSTGRES_PASSWORD`
   - `JWT_SECRET` (at least 32 random characters)
   - `DEMO_PASSWORD` (at least 12 characters)
   - `RAG_POSTGRES_PASSWORD` (URL-safe)
   - `RAG_INGESTION_TOKEN` (at least 32 random characters)
   - The same URL-safe RAG password inside `RAG_DATABASES_JSON`

   The sample maps CRM workspace `1`, which is created by the local demo profile. For an existing non-demo CRM database, replace `1` with its real workspace ID before first startup.

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

   Sign in with `admin@estraos.demo`, `manager@estraos.demo`, or `agent@estraos.demo` and the private `DEMO_PASSWORD` you chose.

## Start one component

Each service folder has its own `compose.yaml` and `.env.example`. Copy the example to `.env`, fill in its `REPLACE_...` values, then run its compose command from that folder.

| Component | Command | Notes |
| --- | --- | --- |
| CRM API + PostgreSQL | `cd real-estate-ai-mvp/backend; docker compose up --build -d` | API is on `http://localhost:8080`. It can use a separately started knowledge service at `http://host.docker.internal:8090`. |
| Web UI | `cd real-estate-ai-mvp/frontend; docker compose up --build -d` | Start the API first. Set `VITE_API_URL` to the browser-reachable API URL, normally `http://localhost:8080/api/v1`. |
| Knowledge API + worker + pgvector | `cd real-estate-ai-mvp/rag; docker compose up --build -d` | Use the same `RAG_INGESTION_TOKEN` as the CRM. The first worker run downloads the embedding model. |

## Stop, rebuild, and reset

```powershell
# Stop containers while preserving databases, files, and models.
docker compose down

# Rebuild after source changes.
docker compose up --build -d

# Remove all local Docker data for this stack. This is destructive.
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
- Knowledge service cannot connect to PostgreSQL: ensure the password inside `RAG_DATABASES_JSON` exactly matches `RAG_POSTGRES_PASSWORD` and is URL encoded.
- Startup is slow only on the first knowledge-worker execution: it is downloading the pinned local embedding model into a named volume.
