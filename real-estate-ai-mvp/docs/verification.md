# Delivery verification

Checks executed on 15 September 2026 against the delivered source:

| Check | Result |
| --- | --- |
| Frontend dependencies | npm installation and audit completed; zero reported vulnerabilities |
| Frontend lint | `npm run lint` passed |
| Frontend tests | `npm test`: 13 passed, including project-dependent unit selection/reset, price precision and navigation focus |
| Frontend production build | `npm run build` passed TypeScript compilation and Vite bundling |
| Backend compilation, tests, package | `mvn verify` passed; runnable JAR produced |
| Backend tests | 24 passed, zero failures/errors/skips: 8 API integration, 13 adapter, 3 reminder-worker tests |
| PostgreSQL | Flyway migration and seed executed on PostgreSQL 17.11; external disposable test database used for the full suite |
| Database constraints | `scripts/verify_database.py` passed all 45 required-table identity/audit/tenant checks and rolled-back constraint probes |
| API acceptance | `scripts/verify_api.py` passed 22 acceptance groups against the running demo API |
| Runtime | Health returned UP; Swagger UI and OpenAPI returned successfully |
| Browser | Login/dashboard/project/inventory/lead views checked; created a persisted lead and booked a site visit through real forms; desktop and narrow layouts inspected |
| Docker | Both image builds attempted but Docker Desktop failed with EOF / unable-to-start errors; image builds and container runtime remain unverified |

API checks cover authentication, revoked sessions, roles, foreign workspace IDs and relationships, validation, numeric generated IDs, inventory uniqueness, lead edits/notes, content publication/history, simulated calls, saved recommendations, overlap rejection, handover creation, cancellation, unavailable inventory and recipient-scoped notifications. Backend tests also cover concurrent bookings and provider failure handling.

All persisted keys are database-generated `BIGINT` identities. Java uses `Long` and JPA `GenerationType.IDENTITY`; API IDs are decimal strings to preserve browser precision. Random opaque request tokens and test credentials are not database keys.

## Repeat checks

Run the commands in the root and backend READMEs. Without Docker, set `TEST_DATABASE_URL`, `TEST_DATABASE_USERNAME`, and `TEST_DATABASE_PASSWORD` to a **fresh empty disposable database for each test run**, then run `mvn verify`. The suite writes fictional records.

For standalone schema verification, set `PSQL_BIN` to your psql executable, `PGHOST`, `PGPORT`, `PGPASSWORD`, `DATABASE_USERNAME`, and `DATABASE_NAME`, then run `python scripts/verify_database.py`. Alternatively use its documented Docker settings. Its constraint probes roll back.

For API acceptance, run a separate demo instance, export its caller-chosen `DEMO_PASSWORD`, and run `python scripts/verify_api.py`. It creates verification records and leaves them in that disposable instance.

## External verification and limitations

RAG, Voice Agent and notification contracts/credentials were unavailable. Local adapter tests verify provisional request/response handling, scope and errors; demo results are explicit mocks, not live calls or deliveries. Configure the URL/key variables in `.env.example`, map actual provider payloads as documented in integration.md, then perform the live-provider acceptance steps there. No production deployment was performed.

PDF registration accepts metadata, editable text and an existing external storage reference; original PDF bytes, upload, extraction and storage authentication belong to an external pipeline. The interface is English with four supported content-language choices. Optional CSV/Excel import is not implemented. Selection lists currently load up to 100 records; larger datasets need searchable paginated selectors. Profile shows account/access details without password management.

After Docker Desktop is healthy, execute both independent image-build commands in the root README and verify health, login, CORS and the workflow using operator-managed PostgreSQL/networking. Native builds do not establish image compatibility.

## Source archive

`python scripts/package_source.py` creates the movable source ZIP. It requires the documented directories, Dockerfiles, environment examples and both migration copies; rejects known runtime credentials supplied through environment variables; excludes generated dependencies, build products, local environment files and Git metadata; validates ZIP CRCs and safe paths; and compares every extracted byte with its source. Actual packaging results are reported with the delivery artifact.
