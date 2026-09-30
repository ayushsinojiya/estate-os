# EstraOS requirements audit

Reviewed 15 September 2026 against `astra_estra_os_mvp_prompt.md`, with the later user instruction replacing UUID database keys with numeric identity keys.

## Conclusion

The delivered application covers the main MVP workflows, but it is not fully complete against every requirement. The earlier delivery wording was too broad. Passing tests establish the scenarios they exercise, not complete requirements coverage. This review changes no application code or existing ZIP.

## Confirmed gaps and defects

| Priority | Finding and impact | Source evidence | Acceptance needed |
| --- | --- | --- | --- |
| High | Document list fetches only the API's default first page (20 records), with no pagination controls. Older documents become unreachable through that page. | `frontend/src/pages/Projects.tsx`, Documents at line 444; `backend/src/main/java/com/estraos/repository/TenantRepository.java`, list defaults | Create more than 20 documents; navigate all pages and open/edit an older record. |
| High | Document processing status is not refreshed from the provider in the UI. The processing endpoint exists, but the UI never calls it; the endpoint also returns the provider response without updating stored status. A queued index operation can appear queued indefinitely. | `frontend/src/pages/Projects.tsx`; `backend/src/main/java/com/estraos/service/EstateService.java:537` | Provider transitions QUEUED to READY or FAILED; UI retrieves and displays the current status/error and preserves consistent document state. |
| High | Visit, handover and recommendation selectors load only the first 100 leads/projects/units/visits. Project filtering happens after fetching those 100 units across the workspace, so even a project's first available unit can be absent. | `frontend/src/pages/SiteVisits.tsx:28`; `Handovers.tsx:33`; `Recommendations.tsx:21` | Search/paginate options server-side; select records beyond the first 100 and preserve existing selected records on edit. |
| High | Failed-call notifications cover an exception while starting a call, but not a successful provider response whose status is FAILED, nor a later refresh transition to FAILED. | `backend/src/main/java/com/estraos/service/EstateService.java:714` and `:799`; FAILED_CALL exists only in the start exception handler | Simulate queued-to-failed and immediate FAILED responses; persist exactly one notification per failure transition, including repeat refresh checks. |
| Medium | Handover detail omits the selected project/unit and assigned agent from the detail presentation, and shows only some customer requirements. Area preferences, possession timeline, purpose and the explicit handover timestamp are absent there. The data exists or is reachable elsewhere, but the required complete handover view is partial. | `frontend/src/pages/Handovers.tsx:208`; backend get/handover methods | Display the selected property, assigned agent, full saved requirements and timestamp directly in handover details. |
| Medium | Schedule view sorts only the current page in the browser. The server defaults to creation-date ordering, so the schedule is not globally chronological across pages. | `frontend/src/pages/SiteVisits.tsx:75,118`; `frontend/src/hooks/useList.ts` | Request scheduledAt ordering before pagination; visits created out of date order must remain chronological across pages. |
| Medium | Audit records have an IP column but the audit service never fills it, even for an available direct client address. Metadata is only a generic description, limiting investigation of updates/failures. | `backend/src/main/java/com/estraos/audit/AuditService.java:15`; migration audit_logs definition | Capture the safely available client address without blindly trusting forwarded headers; retain useful sanitized change/failure metadata. |

## Partial implementation / design limitations needing follow-up

- Inventory structure: buildings, floors and unit types can be created and listed. Units reference a building, but their floor is a free numeric field and no unit-type relation is captured. Created floor/type catalogs do not constrain unit entry. The requirement does not prescribe exact columns, but this is incomplete integration of the inventory model, not a missing table.
- Project context on support records: the migration includes nullable project_id on document/content versions and unit histories/prices, but generic `repo.event()` writes only the immediate parent ID. Project context can be recovered through the parent; direct project_id filtering on those rows will miss records. Workspace/parent foreign keys still exist, so this finding alone is not evidence of cross-tenant access.
- Callback reminders are supported through a lead's manually entered followUpAt. Voice callbackStatus/requirements are stored and displayed; provider callback outcomes are not mapped automatically into lead follow-up scheduling. Whether that automatic mapping is necessary depends on the real service contract.
- Notifications target internal user IDs. Customer SMS/WhatsApp/email confirmation routing is not implemented by the current payload. Customer confirmation status is manually editable, separate from notification delivery.
- Handover changes overwrite handoverAt each time. createdAt survives, but the meaning of original handover time versus latest update should be clarified and represented consistently.
- api_request_logs exists as a table but has no writer. The specification requires the table and proper logging, not explicitly an access-log writer; this is an observability limitation rather than a missing required API.

## Requirement coverage summary

| Area | Assessment |
| --- | --- |
| React/Tailwind frontend, Spring Boot backend, PostgreSQL/Flyway | Present |
| Login/logout, password hashing, JWT, current user, roles, protected UI | Implemented; existing automated coverage |
| Workspace membership and scoped resource access | Implemented; existing isolation/relationship tests; no new penetration test performed |
| Dashboard metrics, activity, follow-ups and demo labels | Present |
| Project CRUD, status, search/filter/sort/pagination, metadata | Present |
| Inventory, availability, duplicates and history | Present with catalog integration limitation above |
| Documents, editable content, versions, publish/unpublish/reindex | Present with pagination and processing-status gaps above |
| Four content languages and RAG language context | Present; interface remains English |
| Lead fields, assignment, notes, timeline, calls, suggestions, visits | Present |
| Voice start/details/transcript/summary/requirements/handover action | Present through provisional adapters; status-triggered notifications incomplete |
| Structured recommendations and published-only RAG scope | Present; selectors limited; real semantic quality unverified |
| Site visits, status changes, conflict checks, schedule | Present with schedule ordering and selector gaps |
| Human handover | Persisted and usable; detail presentation incomplete |
| Notification architecture, delivery records and reminder worker | Present with failure-transition and customer-routing limitations |
| Audit trail | Present; safe IP capture and richer metadata incomplete |
| Required database tables | Existing schema verification covers all 45 required tables; extra session/suggestion tables are present |
| Identifier requirement | Numeric BIGINT identity is correct under the user's later override; remaining opaque random request tokens are not database primary keys |
| Required routes | All listed routes are declared; audit route is additionally available |
| Required frontend test categories | Login, protected routes, projects, lead create/edit, booking, validation, loading/error tests exist |
| Required backend test categories | Auth, roles, tenancy, project/lead/unit/booking/handover/validation and adapters covered by saved test reports |
| Documentation, env examples, migrations, independent Dockerfiles | Present |
| Clean movable source ZIP | Rechecked successfully in this audit |

## Allowed deferrals and external blockers

- CSV/Excel import was explicitly conditional ("if practical"); absent, not a mandatory unfinished item.
- Localized UI text was qualified by "where practical"; English-only UI is a disclosed limitation. Four language labels/storage/context are implemented.
- The document requirements explicitly request metadata and a storage reference. External PDF-byte storage is an allowed architecture; a built-in uploader is not automatically a missing mandatory feature. Storage provisioning and extraction remain external work.
- Actual RAG/Voice/notification contracts and credentials were unavailable. Replaceable REST adapters plus explicit demo mocks meet the specified fallback. Live-provider compatibility and delivery must still be verified after configuration.
- Docker image builds were attempted earlier and blocked by Docker Desktop failure. Native build success does not replace image/runtime verification.
- Profile editing/password management and workspace administration screens were not explicitly required; their absence is not classified as a mandatory gap.

## Evidence and scope of this audit

Read the requirements, route declarations, controller, workflow service/repository, relevant UI/forms, adapters, audit implementation, migration, test sources and saved test reports. This was a source/requirements audit, not a fresh run of all tests or a live-provider test.

Fresh checks: the ZIP opens with valid CRCs; all 93 archived files exactly match current source; no node_modules/target/dist/.git directory appears in the archive; canonical/distributed migrations are byte-identical. Saved backend reports show 24 tests with zero failures/errors/skips. The previous frontend verification reports 13 passing tests plus lint/build; those checks were not rerun in this review.

The current ZIP remains a working MVP delivery with the gaps above, not a fully closed requirements checklist. Fix the confirmed gaps, add focused regression tests, rerun affected checks and rebuild/revalidate the ZIP before claiming full completion.
