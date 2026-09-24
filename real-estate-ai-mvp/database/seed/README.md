# Development seed

The backend's demo-profile initializer supplies repeatable application seed records. It runs only when explicitly selected and requires a caller-provided `DEMO_PASSWORD`; the value is hashed before storage.

## Pune synthetic inventory

`pune_synthetic_properties.sql` adds 25 fictional Pune developments and exactly 1,000 fictional property records to the existing `Westhaven Realty · Demo` workspace. It is intentionally labelled synthetic and uses database-generated BIGINT identity IDs. It does not download, claim, or represent real listings.

Run it only against a local disposable database after the Flyway schema and demo profile have created the workspace:

```sh
psql -v ON_ERROR_STOP=1 -U postgres -d estate_os -f database/seed/pune_synthetic_properties.sql
```

The script is idempotent: a rerun inserts only missing records and verifies that exactly 1,000 of its synthetic units are present. If the local workspace has a different name, edit `target_workspace_name` at the top of the SQL file before running it.

| Account | Role |
| --- | --- |
| `admin@estateos.demo` | ADMIN |
| `manager@estateos.demo` | MANAGER |
| `agent@estateos.demo` | REAL_ESTATE_AGENT |
| `agent2@estateos.demo` | REAL_ESTATE_AGENT in the second workspace only |

Use the same locally supplied demo password for the initial four accounts. The admin belongs to both demo workspaces; the manager and first agent belong to the populated first workspace. No working password or signing secret is included in source. Set `SPRING_PROFILES_ACTIVE=demo` and `INTEGRATIONS_MODE=mock` only for development. Start the application with the database and JWT environment configured as documented in the root README. Existing passwords are preserved on subsequent starts.

The seed is Java-based rather than static credential-bearing SQL. Its source is in the backend configuration package. Reset only an intentionally disposable database if a fresh seed is needed.
