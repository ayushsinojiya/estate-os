# Setup and runtime configuration

## Backend process environment

Review `backend/.env.example`. Its values are placeholders, not working credentials. Load your chosen values into the shell environment or use Docker's `--env-file` support. Spring Boot does not read `.env` files automatically.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | JDBC PostgreSQL URL, such as `jdbc:postgresql://localhost:5432/estateos` |
| `DATABASE_USERNAME` | Dedicated database role |
| `DATABASE_PASSWORD` | Database role password |
| `JWT_SECRET` | Random signing material, at least 32 bytes; required |
| `JWT_TOKEN_MINUTES` | Token lifetime; default 60 minutes |
| `PORT` | HTTP listener; default 8080 |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact browser origins |
| `SPRING_PROFILES_ACTIVE` | Set `demo` only for seeded development, or `test` for isolated tests |
| `DEMO_PASSWORD` | Caller-chosen development account password; required only when seeding demo |
| `INTEGRATIONS_MODE` | `rest` normally; `mock` requires demo/test profile |
| `RAG_SERVICE_URL`, `RAG_API_KEY` | Existing RAG endpoint and bearer credential |
| `VOICE_AGENT_SERVICE_URL`, `VOICE_AGENT_API_KEY` | Existing Voice Agent endpoint and bearer credential |
| `NOTIFICATION_SERVICE_URL`, `NOTIFICATION_API_KEY` | Existing delivery gateway and bearer credential |
| `INTEGRATION_CONNECT_TIMEOUT_MS`, `INTEGRATION_READ_TIMEOUT_MS` | Bounded external HTTP timeout configuration |
| `NOTIFICATION_REMINDERS_ENABLED` | Enable persisted due-reminder dispatch; default true |
| `NOTIFICATION_REMINDER_POLL_MS` | Reminder polling interval in milliseconds; default 60000 |
| File storage | Supply an existing external `storageReference` when registering a document. There is no consumed `FILE_STORAGE_URL` application variable or file-byte upload adapter; configure storage authentication in your external content pipeline. |

For canonical adapter property mappings and response contracts see [integration.md](integration.md). All required REST URLs must be configured in REST mode; there is no silent mock fallback. Protect provider keys and the signing secret with deployment secret management. Do not place any secret in frontend variables.

### Example terminal commands

On PowerShell, use `$env:VARIABLE = 'your-value'` for each variable. On POSIX shells use `export VARIABLE='your-value'`. Generate credentials locally and supply them privately; do not reuse example placeholders or place secrets in shared shell history.

After PostgreSQL is ready and environment is configured:

```sh
cd backend
mvn spring-boot:run
```

Flyway applies the schema. To build a standalone artifact:

```sh
mvn verify
java -jar target/estateos-api-1.0.0.jar
```

## Frontend environment

`VITE_API_URL` is the browser's API base URL including `/api/v1`. A relative `/api/v1` works with a same-origin reverse proxy. During local development, Vite proxies this path to `API_PROXY_TARGET`, which defaults to `http://localhost:8080`. An absolute browser URL must be reachable by the user's browser and allowed by backend CORS.

```sh
cd frontend
npm ci
npm run dev
```

Use `.env.local` for private local configuration (it is excluded from distribution). Frontend URL settings are baked into the production bundle. Restart the dev server after changing them; rebuild the container for production changes.

## PostgreSQL and migrations

Use PostgreSQL 17 and an empty application database for the first run. The application database role needs schema/table/index creation privileges for Flyway migrations. Apply future versioned migrations through Flyway, never edit a migration already deployed. No destructive reset occurs during normal startup.

See [database instructions](../database/README.md) for the canonical schema, seed mode and safe development reset procedure. Backup and restore policy is a deployment responsibility.

## Docker networking

Build each image using its own folder as context, as shown in the root README. The backend image connects to operator-managed PostgreSQL and providers. The frontend image serves static assets. When those containers run separately, choose reachable network names for server-side URLs and browser-reachable addresses for the frontend API URL. Configure matching allowed origins.

Use TLS at the deployment edge. Run demo and test installations separately from real customer data. Confirm the documented acceptance flow and cross-workspace tests before deployment.
