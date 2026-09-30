# External service integration

The existing RAG, Voice Agent and notification service API contracts, URLs and credentials were not provided. The REST mappings below are **provisional contracts**, not verified provider APIs. Replace the mappings in `backend/src/main/java/com/estraos/integration/Rest*ServiceClient.java` to match the actual services. The application does not implement an embedding engine, semantic search engine, voice agent, prompts or provider administration.

## Configuration

| Environment variable | Spring property | Meaning |
| --- | --- | --- |
| `INTEGRATIONS_MODE` | `app.integrations.mode` | `rest` (default) or explicit `mock` |
| `RAG_SERVICE_URL` | `app.integrations.rag.url` | RAG base URL |
| `RAG_API_KEY` | `app.integrations.rag.api-key` | Optional service bearer credential |
| `VOICE_AGENT_SERVICE_URL` | `app.integrations.voice.url` | Voice Agent base URL |
| `VOICE_AGENT_API_KEY` | `app.integrations.voice.api-key` | Optional service bearer credential |
| `NOTIFICATION_SERVICE_URL` | `app.integrations.notification.url` | Notification gateway base URL |
| `NOTIFICATION_API_KEY` | `app.integrations.notification.api-key` | Optional service bearer credential |
| `INTEGRATION_CONNECT_TIMEOUT_MS` | `app.integrations.connect-timeout-ms` | Connection timeout, default 3000 milliseconds |
| `INTEGRATION_READ_TIMEOUT_MS` | `app.integrations.read-timeout-ms` | Response timeout, default 10000 milliseconds |
| `SPRING_PROFILES_ACTIVE` | Spring active profiles | `demo` or `test` is required for mock mode |

REST mode validates all three URLs at startup. Absolute HTTP(S) URLs are required; embedded credentials, fragments and query parameters are rejected. Use HTTPS for deployed service connections. Keys are sent only as `Authorization: Bearer <key>`; an empty key supports a gateway with separate network authentication. Configure the real provider's required credentials before enabling REST mode. No automatic fallback to mocks occurs. Mock mode is rejected without an explicit `demo`/`test` profile, and rejected with `prod`/`production` even if a demo profile is also active.

All HTTP requests use JSON, explicit connect/read timeouts (1–120000 milliseconds), no redirect following, and no automatic retry. Provider bodies, credentials, request data and original exceptions are not exposed in application errors. Upstream rejection/unavailability/invalid JSON produce sanitized `INTEGRATION_*` errors with HTTP 502; timeouts produce HTTP 504. An optional `requestId` of 1–128 letters, digits, underscores or hyphens is forwarded as `Idempotency-Key`. Production callers should provide stable persisted request IDs for side effects and reconcile provider state after a timeout before retrying. A timeout does not prove the provider did not perform the action.

The implementation uses Spring `RestClient` and the Java HTTP client request factory. Timeout support is documented in [Spring's JDK request factory API](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html).

## Scope and language contract

Every request has a positive 64-bit integer `workspaceId` established by the authenticated application service. Related resources are authorized in the application's database before the adapter is called. Document operations require positive 64-bit integer `projectId` and `documentId` (`resourceId` is an accepted internal alias). `language` is `en`, `hi`, `gu` or `mr`, defaulting to `en`. Search may cover the authorized workspace or a single project. The adapter does not authorize user membership by itself; do not expose it as an unauthenticated proxy.

## RAG endpoints

All paths are appended to `RAG_SERVICE_URL`; all methods are POST. Search/status use POST to carry complete scope in JSON and avoid putting customer queries in URL logs.

| Interface method | Endpoint | Payload additions | Expected response |
| --- | --- | --- | --- |
| `searchKnowledgeBase` | `/v1/knowledge/search` | `query`, `publishedDocumentIds`, optional `projectId`; forced `publishedOnly:true,status:"PUBLISHED"` | `{"results":[...]}` |
| `indexPublishedContent` | `/v1/content/index` | Document context, `content`, optional `version`,`storageReference`,`pageReference`; forced published scope | `{"status":"QUEUED","documentId":"..."}` |
| `reindexDocument` | `/v1/documents/reindex` | Document context and current published content/reference; forced published scope | `{"status":"QUEUED","documentId":"..."}` |
| `getProcessingStatus` | `/v1/documents/status` | Document context | `{"status":"COMPLETED","documentId":"..."}` |
| `unpublishContent` | `/v1/content/unpublish` | Document context | `{"status":"UNPUBLISHED","documentId":"..."}` |

Database identities use PostgreSQL BIGINT identity columns and Java Long. Integration JSON transmits them as decimal strings to preserve precision for JavaScript consumers; numeric integral input is accepted. External provider IDs remain opaque strings. Example search request:

```json
{
  "workspaceId": "101",
  "projectId": "201",
  "language": "gu",
  "query": "Which amenities are available?",
  "publishedOnly": true,
  "status": "PUBLISHED",
  "publishedDocumentIds": ["301"]
}
```

Example provider search response:

```json
{
  "results": [{
    "workspaceId": "101",
    "projectId": "201",
    "documentId": "301",
    "status": "PUBLISHED",
    "language": "gu",
    "text": "Published source excerpt",
    "pageReference": "4",
    "score": 0.91
  }]
}
```

The application supplies the allowlist of currently published document IDs from its own scoped database. Missing allowlist is rejected; an empty list allows no citations. Results without matching workspace/project/published status/allowed document ID are discarded. The adapter relays only the filtered `results` and `mock:false`; a top-level provider answer is intentionally excluded because its facts cannot be attributed to validated citations. The provider must independently enforce tenant filters and published-only indexing/retrieval. Explicit draft indexing is rejected before HTTP. A production unpublish operation must remove/tombstone the document from retrieval; the application allowlist additionally excludes unpublished records. Verify version replacement semantics with the actual provider before deployment.

RAG processing statuses are provider-owned strings; agree on QUEUED, PROCESSING, COMPLETED and FAILED (including a sanitized error field) when connecting the real provider. The demo returns COMPLETED/UNPUBLISHED with `mock:true` and does not change an external index. Demo searches return an empty `results` list with a clear mock label, rather than invented brochure facts.

## Voice Agent endpoints

**Status: implemented and connected.** Unlike the RAG and notification mappings above, this
contract is no longer provisional. The voice agent in `last try/real-estate-voice-agent` serves
both endpoints (`app/main.py`), and `tests/test_crm_integration.py` on that side covers them.


`POST /v1/calls/outbound` receives:

```json
{
  "workspaceId": "101",
  "leadId": "401",
  "phone": "+919000000001",
  "language": "en",
  "requestId": "persisted-request-token"
}
```

Optional authorized `projectId` and customer context are forwarded unchanged. Response must contain `externalId`, matching `workspaceId` and `status`; it may contain `leadId`, `summary` (string), `transcript` (string), `requirements` (object), `outcome`, `recommendedProperties`, `handoverStatus`, and `callbackStatus`.

`POST /v1/calls/details` receives `workspaceId`, `externalId`, optional `projectId` and `language`. It returns the same detail structure, with matching external ID and workspace required. For example:

```json
{
  "externalId": "provider-call-123",
  "workspaceId": "101",
  "status": "COMPLETED",
  "outcome": "QUALIFIED",
  "summary": "Customer requested an agent follow-up.",
  "transcript": "Provider transcript text",
  "requirements": {"bhk": 2, "intent": "BUY", "language": "en"},
  "handoverStatus": "PENDING",
  "callbackStatus": "NOT_REQUESTED"
}
```

The application persists returned details and provides an explicit refresh action. No webhook or provider event subscription is assumed. Adapt these endpoints if the existing service uses GET, nested payloads or separate transcript APIs. Demo start creates an in-memory, deterministic, explicitly labeled conversation without placing any call; the application persists its received details. Demo provider refresh works only for calls started during the same process lifetime and workspace. Mock call data is a demonstration fixture, not customer-confirmed requirements.

## Voice agent access to this API

The voice agent is also a *client* of this API: during a call it resolves the caller to a lead, and
after the call it delivers the record. It authenticates as an ordinary principal.

**Authentication.** `ServiceAccountProvisioner` creates a user from `SERVICE_ACCOUNT_EMAIL` /
`SERVICE_ACCOUNT_PASSWORD` and makes it a `MANAGER` of `SERVICE_ACCOUNT_WORKSPACE_ID`, creating
that workspace when `SERVICE_ACCOUNT_WORKSPACE_NAME` is set and the ID does not exist yet. The
agent calls `POST /api/v1/auth/login`, caches the token, and renews it before expiry and on any
401. There is no machine-only credential path and no bypass in `TenantContext`: session
revocation, workspace membership, role checks and audit attribution all apply unchanged. Revoking
the agent's access is deleting its `workspace_members` row or disabling the user.

Leave `SERVICE_ACCOUNT_EMAIL` blank to disable machine access entirely.

| Endpoint | Used for |
| --- | --- |
| `POST /api/v1/leads/find-or-create` | Resolve a caller's number to a lead, creating one on first contact. Serialized on the workspace advisory lock, so simultaneous calls from one number cannot produce duplicate leads. Returns the lead plus `created`. |
| `POST /api/v1/calls/ingest` | Deliver the post-call record: transcript, summary, captured requirements, lead score, do-not-call outcome. |

`calls/ingest` is idempotent on the agent's own session identifier. A record whose `callId`,
`voiceSessionId` or matching `externalId` is already known updates that `voice_sessions` row
instead of creating a second one, so the agent's retry outbox can resend a record safely after a
timeout. A record naming a call already recorded against a different lead is rejected with 409.

Ingest also moves the lead forward: it merges captured requirements into `leads.data` and advances
status, but only from `NEW` or `CONTACTED`, so a later call cannot reopen a lead an agent has
already qualified or handed over. `doNotCall` sets `NOT_INTERESTED`.

Payload field names are this API's camelCase; the agent maps its internal snake_case record onto
them in `app/crm/client.py`. Because `fail-on-unknown-properties` is enabled, a new field must be
added to `Requests.CallIngest` and to that mapping together.

### Not yet connected

These voice-agent operations still read the agent's local inventory snapshot, because this API has
no endpoint for them yet. They are listed in `MILESTONE_2` in `app/crm/client.py`:

| Operation | What this API needs |
| --- | --- |
| `get_project`, `get_availability`, `get_price`, `search_units` | Read endpoints shaped for an unknown caller: budget, BHK and locality rather than IDs. |
| `get_site_visit_slots`, `get_slot`, `book_site_visit` | **A bookable-slot model.** `appointments` stores a free-form `scheduled_at` and a required `agent_id`; the agent's booking flow needs capacity-bounded slots and a rule for assigning an agent with no human in the loop. This is the largest remaining gap. |
| `update_lead`, `create_callback` | Field-merge semantics on `PUT /api/v1/leads/{id}`, and a callback resource. |
| `mark_do_not_call` | A DNC endpoint. Until then suppression is local to the agent only, and **a number marked do-not-call on a call is not reflected in this CRM** beyond the lead status set by ingest. |

## Notification endpoint

`POST /v1/notifications` receives `workspaceId`, `notificationId`, `recipientUserId`, `type` and `message`; the adapter adds `language:"en"` when not supplied. Identity values are decimal strings and `recipientUserId` may be null for a general notification. Optional authorized `projectId`, `language`, `recipient`, `entityId`, `channel` and `requestId` fields are forwarded when supplied by a caller. The gateway must resolve the scoped user ID to a delivery address and choose a configured route, or the REST adapter must be extended to map an authorized contact address to the actual provider contract. Customer notification delivery requires an explicit customer recipient; an agent notification record does not prove the customer was contacted. Response requires `status` and may include `externalId`, for example `{"status":"QUEUED","externalId":"delivery-123"}`. An accepted response is not proof of final delivery; map actual provider delivery states when connecting a gateway. The mock returns `MOCK_DELIVERED` and `mock:true`, sends no SMS/email/WhatsApp, and is displayed as demonstration delivery. `NotificationReminderService` polls persisted notification rows with `status=SCHEDULED` and a due `dueAt` timestamp. It claims up to 20 rows using `FOR UPDATE SKIP LOCKED`, delivers with stable `notification-{id}` idempotency keys, and records delivery, outbox and audit results. The worker defaults to enabled with a 60000 ms interval; configure `app.notifications.reminders-enabled` and `app.notifications.reminder-poll-ms` to control it. Failed delivery is recorded as FAILED for review, without automatic retry. Actual delivery callbacks and provider status reconciliation remain unverified pending the provider contract.

## Original document storage

The MVP registers existing PDF metadata and a `storageReference`; it does not upload PDF bytes or fetch arbitrary document URLs. Store the original in your controlled file/object storage first, then register the reference with the project and editable content. Prefer opaque keys such as `workspaces/<workspace-id>/projects/<project-id>/documents/<document-id>/brochure.pdf`. Configure `FILE_STORAGE_URL` for your storage service and implement permission-checked download/signed URL generation there. Do not place long-lived signed URLs or credentials in metadata. The RAG service requires scoped read permission to the supplied storage reference; the application cannot verify external bytes, file type, retention, antivirus scanning or storage permissions from metadata alone. Human-edited content and versions remain in PostgreSQL; embeddings and parsing remain provider-owned.

## Verification and remaining blockers

`mvn -Dtest=IntegrationAdapterTest test` runs local HTTP contract tests and mock tests. These exercise endpoint/body/auth/idempotency mapping, tenant and publication response filtering, invalid configuration, mock gating, malformed provider JSON, sanitized errors, and a real local HTTP timeout. They never call the external RAG/Voice Agent/notification services or place calls/send messages.

Real-service verification remains blocked by unavailable actual contracts, URLs, credentials and test tenants. After receiving them:

1. Confirm endpoint/method/JSON/authentication, languages, processing states, idempotency and tenant enforcement with each provider. Update only the appropriate REST adapter mapping and contract tests.
2. Set `INTEGRATIONS_MODE=rest`, provider URLs/keys and timeouts against isolated provider test environments. Start the backend and confirm configuration validation and health.
3. Register an owned storage reference, publish content and verify indexing/status. Search using each supported language and check source citations. Test another workspace and draft/unpublished content; neither may appear. Test an unpublish while previously indexed content exists.
4. With explicit authorization for a provider test phone, start one call, capture external ID, refresh details and confirm persisted transcript/summary/requirements and workspace isolation. Check timeout reconciliation before any retry.
5. With authorized test recipients, send a visit/assignment notification, verify provider status against the stored delivery record, verify one persisted due reminder is dispatched exactly once, and connect actual delivery callbacks if supported.
6. Remove test-only credentials and configure deployment secrets outside source control. Record the provider versions and observed results; transport tests alone do not certify real-provider compatibility.
