# Real-estate voice agent + CRM

Two services that were built separately and are now connected.

| | Path | Stack |
| --- | --- | --- |
| **Voice agent** ("Riya") | `last try/real-estate-voice-agent` | Python, FastAPI, VoiceLink telephony |
| **CRM** (EstraOS) | `real-estate-ai-mvp` | Java 21 / Spring Boot, PostgreSQL, React |

## How they talk

The **CRM owns the contract**. It is the system of record for every business entity; the agent
reads through it and writes back to it.

```
 CRM ──► agent    POST /v1/calls/outbound     start a call for a lead
                  POST /v1/calls/details      fetch transcript, summary, outcome
                  auth: VOICE_AGENT_API_KEY as a bearer token

 agent ──► CRM    POST /api/v1/leads/find-or-create   resolve a caller to a lead
                  POST /api/v1/calls/ingest           deliver the post-call record
                  auth: service-account login at /api/v1/auth/login
```

The agent authenticates as an ordinary CRM principal rather than through a machine-only side door,
so workspace membership, role checks, session revocation and audit attribution apply to it exactly
as they do to a human user. `ServiceAccountProvisioner` creates that login on boot.

Full contract, including what is **not** connected yet:
[`real-estate-ai-mvp/docs/integration.md`](real-estate-ai-mvp/docs/integration.md).

## Running locally

For the Docker-based full stack or individual service commands, credential templates,
ports, and reset instructions, follow [LOCAL_SETUP.md](LOCAL_SETUP.md). It is the
recommended local setup path.

```bash
# CRM — needs a PostgreSQL on :5432
cd real-estate-ai-mvp/backend && cp .env.example .env   # fill in, then export
mvn spring-boot:run

# Voice agent
cd "last try/real-estate-voice-agent"
cp .env.example .env            # set CRM_MODE=http and the CRM_SERVICE_* values
uvicorn app.main:app --port 8081
```

Set `CRM_SERVICE_EMAIL` / `CRM_SERVICE_PASSWORD` on the agent to the same values as
`SERVICE_ACCOUNT_EMAIL` / `SERVICE_ACCOUNT_PASSWORD` on the CRM, and `CRM_WORKSPACE_ID` to
`SERVICE_ACCOUNT_WORKSPACE_ID`. Point the CRM's `VOICE_AGENT_SERVICE_URL` at the agent and set its
`VOICE_AGENT_API_KEY` to the agent's `ADMIN_API_TOKEN`.

`PROVIDER_MODE=fake` and `CRM_MODE=mock` run the agent entirely offline.

## Deploying

Azure Container Apps, one command: [`deploy/azure/README.md`](deploy/azure/README.md).

## Tests

```bash
cd "last try/real-estate-voice-agent" && .venv/bin/python -m pytest      # 206 tests
cd real-estate-ai-mvp/backend && mvn test                               # needs Docker for Testcontainers
```

`tests/test_crm_integration.py` and `IntegrationAdapterTest` cover the seam from each side.
