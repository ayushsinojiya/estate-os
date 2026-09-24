# PostgreSQL schema and demo seed

PostgreSQL 17 is the supported verification target. database-generated BIGINT identity identifiers, UTC timestamps, audit fields, unique contact/unit constraints and tenant-scoped foreign keys are included. There are no RAG embedding tables; the existing RAG service owns those.

## Migration source

The executable migration source is `backend/src/main/resources/db/migration/`. Matching SQL snapshots are included in `database/migrations/` for inspection and database handoff. Do not independently apply both copies. The backend uses Flyway and validates migration history on normal startup.

Create an empty database with a dedicated role, set `DATABASE_URL`, `DATABASE_USERNAME`, `DATABASE_PASSWORD` and other required backend configuration, then run:

```sh
cd backend
mvn spring-boot:run
```

Flyway applies pending migrations before the API is ready. It does not drop/reset a database. Use the backend's matching Flyway version and original migration files for later upgrades; do not edit applied migrations or manually mark failed changes successful.

## Development seed

Seed data is application-managed so passwords can be hashed from caller-provided input, rather than embedded in SQL. Set `SPRING_PROFILES_ACTIVE=demo`, `INTEGRATIONS_MODE=mock`, and a strong `DEMO_PASSWORD`, then start the backend against a disposable database. The seed creates demo admin/manager/agent accounts, a labeled workspace, properties, inventory, knowledge, leads, call history, appointments and notifications. See `seed/README.md` for account details.

The normal profile does not seed demo users. Existing user passwords are not silently overwritten by changing `DEMO_PASSWORD`. No real credentials are distributed.

## Verification

Backend integration tests start isolated PostgreSQL through Testcontainers by default. Alternatively configure a fresh empty disposable database using `TEST_DATABASE_URL`, `TEST_DATABASE_USERNAME`, and `TEST_DATABASE_PASSWORD`, as described in the backend README:

```sh
cd backend
mvn verify
```

The optional `scripts/verify_database.py` checks the required tables, identity/audit/tenant columns, cross-workspace foreign keys and key uniqueness/price constraints against a disposable database. Docker mode uses `DB_CONTAINER`, `DATABASE_USERNAME`, and `DATABASE_NAME`. Native mode uses `PSQL_BIN`, `PGHOST`, `PGPORT`, `PGPASSWORD`, `DATABASE_USERNAME`, and `DATABASE_NAME`. Data probes roll back. The API acceptance script verifies application-level authorization and booking rules.

## Development reset

Only for an explicitly disposable development database: stop its application, confirm the exact database/container identity, and recreate that dedicated database through your database administration tooling. Then rerun migrations and demo seed. No reset script is supplied or invoked automatically. Preserve any data you need before a reset; do not use this procedure on shared or production databases.
