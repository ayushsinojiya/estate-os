# Troubleshooting

| Symptom | Check |
| --- | --- |
| Backend exits with unresolved environment property | Set required variables in the actual process environment; a `.env` file alone is not loaded by Spring Boot. |
| PostgreSQL connection refused | Database process, JDBC host/port/database, credentials and container network reachability. `localhost` inside a container refers to that container. |
| Migration fails | Read the first Flyway/PostgreSQL error; use an empty compatible database or resolve schema history deliberately. Never reset production to fix a development issue. |
| JWT configuration rejected | Supply a sufficiently long randomly generated secret, identical across API replicas. Do not use an example placeholder. |
| Mock mode rejected | Mock providers require explicit demo/test profile as well as `INTEGRATIONS_MODE=mock`. |
| Real integration startup fails | Configure all required service URLs and keys; consult integration.md for exact variable names and provisional contracts. |
| Browser says network error | Verify `VITE_API_URL`, API health, exact CORS origin and TLS/mixed-content rules. Rebuild frontend after changing Vite variables. |
| Login succeeds but resource access is forbidden | Select a workspace returned by login and send its header; verify membership role. |
| Demo password does not work after changing the variable | Seeding does not silently overwrite an existing user's password. Use the original demo password or a new disposable database. |
| Site visit returns 409 | Check agent/lead overlap, current unit availability, and related-resource consistency. Choose another time or available unit. |
| RAG search returns no knowledge | Publish content, verify indexing/processing and language, and inspect adapter configuration. Demo mocks intentionally do not invent document knowledge. |
| Provider response cannot be used | The supplied REST contract is provisional. Map the adapter to your actual service's schema and verify tenant/published scope. |
| Backend integration tests cannot find Docker | Start Docker Desktop, select Linux containers and verify `docker info`. PostgreSQL tests need a working Docker endpoint. |
| Frontend dependencies report unsupported Node | Use Node 22 LTS or the minimum documented in the frontend package. Run `npm ci` using the included lockfile. |

Health exposes status without private database/provider details. Consult backend logs locally; do not paste credentials, tokens or customer transcripts into public issue reports. External provider failures are sanitized before reaching the UI.
