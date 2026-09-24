# API guide

The interactive, generated endpoint schema is available at `/swagger-ui.html`; JSON OpenAPI is served at `/v3/api-docs`. All business routes are under `/api/v1`.

## Authentication and workspace context

`POST /auth/login` accepts `{ "email": "...", "password": "..." }`. Its response contains a token, a user DTO and available workspaces with membership roles. Send `Authorization: Bearer <token>` and `X-Workspace-Id: <workspace ID>` on workspace-scoped requests. `GET /auth/me` returns current identity; `POST /auth/logout` ends the API session. `GET /workspaces` and `GET /members` provide authorized context for workspace and assignment controls.

Workspaces are validated against membership on the server. Each related record is validated within that context. IDs from a different workspace cannot grant access. Project, unit and knowledge writes require ADMIN or MANAGER; REAL_ESTATE_AGENT may manage lead operations. Audit viewing is restricted to ADMIN/MANAGER.

## Resources

| Resource | Operations |
| --- | --- |
| `/projects` | Search/filter/sort/page, create, detail/update by ID; scoped buildings, floors, unit-types, units, documents |
| `/units` | Inventory list/create/detail/update and status history |
| `/leads` | List/create/detail/update, notes, activity history, saved recommendations |
| `/documents` | Register metadata/reference, detail/list, editable content, publish/unpublish, versions, reindex, processing status |
| `/calls` | History/detail, outbound start and refresh through voice adapter |
| `/recommendations/search` | Structured availability matching plus scoped published document knowledge |
| `/site-visits` | List/schedule/create/detail/update, reschedule/cancel/completed/no-show |
| `/handovers` | List/create/detail/update with agent, lead and visit context |
| `/notifications` | List delivery/read state and mark read |
| `/dashboard` | Persisted summary metrics, upcoming visits/follow-ups and recent activities |
| `/audit-logs` | Workspace-scoped operational audit history |

Lists use `{items,total,page,size}` with zero-based pages. Main list queries accept `search`, `status`, `page`, `size` and supported sorting. IDs are positive database-generated BIGINT values, represented as decimal strings in API responses to preserve JavaScript precision; timestamps are ISO 8601 UTC. Monetary values are INR, area is square feet. Language codes are `en`, `hi`, `gu` and `mr`.

Mutations use validated request DTOs. Invalid input returns 400, unauthenticated requests 401, insufficient access 403, unknown scoped resources 404, and conflicting operations 409. Error bodies use `{timestamp,status,code,message,details}`. Do not infer resource existence across workspaces from a forbidden/not-found response.

## Booking and recommendation invariants

Recommendations only include available units meeting structured requirements. Saving suggestions and booking recheck resource context/availability. A site visit identifies a lead, project, optional unit, agent, UTC scheduled time and duration. Active agent or lead overlaps are rejected. Cancellation releases the scheduling conflict. Handover references must agree with the selected lead/project/visit.

## Provider payloads

See [integration.md](integration.md) for exact provisional adapter endpoints and JSON. Do not expose provider tokens or pass arbitrary provider URLs from a browser. The API supplies workspace, project, language and published-document scope.

For a runnable sequence of request examples and assertions, inspect [verify_api.py](../scripts/verify_api.py). It intentionally requires a disposable demo installation.
