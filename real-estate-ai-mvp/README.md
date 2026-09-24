# EstateOS

A multi-workspace real-estate operations MVP for capturing and qualifying leads, reviewing AI call results, recommending available properties, scheduling site visits, and handing customers to a human real-estate agent. The buying and legal process is outside this application.

## Contents

- `frontend/`: React, TypeScript, Tailwind, routed UI, API client, tests and frontend Dockerfile.
- `backend/`: Java 21, Spring Boot, JWT security, business APIs, Flyway migrations, tests and backend Dockerfile.
- `database/`: migration distribution and development seed instructions.
- `docs/`: architecture, API, setup, integration contracts, verification and troubleshooting.
- `scripts/`: repeatable acceptance verification and source packaging utilities.

## Prerequisites

Java 21, Maven 3.9+, Node.js 20.19+ (Node 22 recommended), npm, and PostgreSQL 17. Backend integration tests use Docker by default or a fresh external test database configured as described in backend/README.md. Python 3.10+ is optional for the API acceptance script.

## Local setup

1. Create an empty PostgreSQL database and a dedicated database user with migration privileges. Do not reuse a production database for demo/testing.
2. Review `backend/.env.example` and set its variables in the backend process environment. Spring Boot does not automatically load `.env` files. Required values are `DATABASE_URL` (JDBC URL), `DATABASE_USERNAME`, `DATABASE_PASSWORD`, and a sufficiently long random `JWT_SECRET`.
3. For explicitly simulated providers and seeded data, set `SPRING_PROFILES_ACTIVE=demo`, `INTEGRATIONS_MODE=mock`, and a strong, locally chosen `DEMO_PASSWORD`. Demo mode is not for production.
4. Start the API:

```sh
cd backend
mvn spring-boot:run
```

Flyway applies versioned migrations automatically. Normal startup never resets existing data. For migration-only operational instructions and seed behavior, see [database/README.md](database/README.md).

5. In another terminal, configure `frontend/.env.local` using the safe example, then run:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Set `VITE_API_URL=http://localhost:8080/api/v1` for this local arrangement. API CORS must allow the exact frontend origin. Frontend environment values are public build-time configuration, so never put secrets in them.

### Development accounts

With demo seeding enabled, sign in using `admin@estateos.demo`, `manager@estateos.demo`, or `agent@estateos.demo` and the `DEMO_PASSWORD` you provided. No password is distributed. The demo workspace and mock call/delivery behavior are labeled. See backend documentation for seeding safeguards and password requirements.

## Tests and builds

```sh
cd frontend
npm ci
npm run lint
npm test
npm run build
```

```sh
cd backend
mvn verify
mvn package
```

For the full API workflow, start a disposable demo installation and set `DEMO_PASSWORD` in your terminal, then run from the project root:

```sh
python scripts/verify_api.py
```

This creates verification records and does not delete them. Never run it against production. `API_URL` may override its default `http://localhost:8080/api/v1`. See [docs/verification.md](docs/verification.md) for checks actually executed for this delivery.

## Independent Docker builds

Run from the project root:

```sh
docker build -t estateos-api ./backend
docker build --build-arg VITE_API_URL=http://localhost:8080/api/v1 -t estateos-web ./frontend
```

Create a private runtime environment file from `backend/.env.example`, replace all placeholders, and keep it outside versioned/distributed source. Then:

```sh
docker run --rm --env-file backend.env -p 8080:8080 estateos-api
docker run --rm -p 3000:8080 estateos-web
```

Set `CORS_ALLOWED_ORIGINS=http://localhost:3000` for the second arrangement. The browser must be able to reach `VITE_API_URL`; Docker-internal hostnames are generally unsuitable for browser URLs. Configure PostgreSQL and provider URLs so they are reachable from the backend container. Networking, external services and database lifecycle are operator-managed. No root Compose workflow is required.

## API and integrations

- Health: `http://localhost:8080/actuator/health`
- OpenAPI: `http://localhost:8080/v3/api-docs`
- Swagger UI: `http://localhost:8080/swagger-ui.html`
- [API overview](docs/api.md)
- [External service contracts and verification](docs/integration.md)
- [Architecture and tenant boundary](docs/architecture.md)
- [Setup details](docs/setup.md)
- [Troubleshooting](docs/troubleshooting.md)

The existing RAG and Voice Agent contracts were not provided. The supplied REST contracts are adapter boundaries to map to your services, not claims of live-provider compatibility. Configure provider URLs/authentication and verify the documented payloads before enabling real outbound calls or notifications. Original PDFs are referenced in external storage; document registration does not upload file bytes to that storage provider.

## Manual acceptance

Log in → dashboard → project → available units → register a PDF storage reference → edit/publish content → create a lead → review call transcript/summary → find and save recommendations → book a site visit → assign a human agent → create a handover → inspect notifications and history. Check a manager/admin workflow and an agent workflow separately. Confirm that switching workspaces clears prior data and that another workspace's resource IDs are rejected.

Production preparation includes supplying real service contracts/credentials, external PDF storage, TLS/reverse proxy, backups, observability and deployment-specific access controls. Known operational limits and external verification steps are documented; no production deployment is performed by these build commands.
