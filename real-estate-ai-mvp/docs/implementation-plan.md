# Implementation plan

## Architecture and assumptions

Independent React/TypeScript/Vite/Tailwind frontend; Spring Boot 3.5, Java 21, Spring Security JWT, JPA, PostgreSQL and Flyway backend. database-generated BIGINT identity keys, UTC timestamps, membership-verified workspace context, scoped queries and related-resource validation protect every tenant resource. No AI engine implementation. Currency INR, area square feet.

Java 21, Maven 3.9, Node/npm and PostgreSQL 17 were used for verification. Full database tests used a dedicated native PostgreSQL instance after Docker Desktop became unavailable. Existing databases and containers were not modified. No Git operations were performed.

RAG/voice/notification contracts and credentials are unavailable. Provide explicit demo/test mocks and configurable provisional REST adapters. Document registration stores metadata and existing storage reference; the external storage service owns original bytes. Demo users require a caller-provided password and explicit demo profile. Production secrets must be supplied through environment variables.

## Ownership

Backend engineer owns backend except integration package/tests. Frontend engineer owns frontend. Integration engineer owns com.estateos.integration and its tests, docs/integration.md. Coordinator owns infrastructure/docs, end-to-end QA, security review and ZIP. Coordinate any shared-boundary edits.

## Acceptance checklist

- [x] Phase 1: read brief, inspect workspace, verify write access, plan architecture and contract.
- [x] Phase 2: backend security, schema, memberships and role checks; PostgreSQL migrations pass.
- [x] Phase 3: frontend navigation, authentication, protected routes, API client and accessible states.
- [x] Phase 4: persisted property/inventory/knowledge/lead/call/recommendation/visit/handover/notification/dashboard workflows.
- [x] Phase 5: replaceable external adapters, bounded timeouts, explicit mocks, adapter tests.
- [x] Phase 6: Dockerfiles, env examples, database seed and complete developer documentation.
- [x] Phase 7: frontend lint/tests/build, backend compile/tests/package, PostgreSQL/API checks and health passed; Docker builds attempted and blocked by engine failure.
- [x] Phase 8: resolve application failures and rerun affected checks.
- [x] Phase 9: review membership, authorization, related-resource ownership, published-only retrieval, booking conflicts and secrets.
- [x] Phase 10: clean source ZIP, archive integrity and extraction verification (93 source files).

## Shared API contract

Base /api/v1. Authorization Bearer token, X-Workspace-Id header for tenant endpoints; validate membership each request. JSON DTOs, camelCase; list envelope {items,total,page,size}; zero-based pagination, search/status/sort query parameters. Error {timestamp,status,code,message,details}. Money INR; area square feet.

- POST /auth/login {email,password} returns {token,user:{id,name,email},workspaces:[{id,name,role}]}; GET /auth/me returns user/workspaces; POST /auth/logout invalidates session and audits.
- GET /workspaces and /members. Members {id,name,email,role} with id=user ID.
- /projects list/create and /projects/{id} get/update. Fields name,description,location,developer,possessionDate,amenities (string),mediaUrl,status. Scoped /projects/{id}/buildings, /floors, /unit-types, /units, /documents. Building name, floor number, unit-type name.
- /units list/create and /units/{id} get/update. Fields projectId,buildingId,unitNumber,bhk,area,floor,facing,price,status,propertyType. /units/{id}/history.
- /leads list/create and /leads/{id} get/update. Fields name,phone,email,language,intent,budgetMin,budgetMax,location,propertyType,bhk,areaMin,areaMax,possessionTimeline,purpose,urgency,status,source,assignedAgentId,tags (string),notes,followUpAt. GET /leads/{id}/activities; POST /leads/{id}/notes {text}.
- /documents list/create/get; fields projectId,title,fileName,storageReference,language,pageReference,content. PUT /documents/{id}/content {content,language,pageReference}; POST /publish,/unpublish,/reindex suffixes; GET /versions,/processing-status suffixes.
- /calls list/get, POST {leadId} starts outbound. POST /calls/{id}/refresh. Call summary,transcript,requirements,outcome,status,externalId,leadId.
- POST /recommendations/search accepts leadId or lead preference fields plus query/language/projectId; returns {items:[{unit,project,reason}],knowledge:[],mock:boolean}. POST /leads/{id}/recommendations {unitIds:[]} stores suggestions.
- /site-visits list/create and /site-visits/{id} get/update: leadId,projectId,unitId(optional),agentId,scheduledAt,durationMinutes,notes,status; response confirmationStatus,notificationStatus. Validate availability and agent/lead overlap.
- /handovers list/create and /handovers/{id} get/update: leadId,agentId,projectId,unitId,appointmentId,notes,questions,status; detailed associated lead/calls/suggestions/visits.
- /notifications list, POST /notifications/{id}/read; /audit-logs list; /dashboard returns metrics,recentActivities,upcomingVisits,followUps,conversionSummary,demo.

ADMIN/MANAGER manage projects/units/documents and view audit. All roles manage leads, visits, calls and handovers within workspace. No hard deletes. History/event logs capture changes.

## Integration contract

Package com.estateos.integration. Interfaces accept and return Map<String,Object> for provisional provider payloads. Each method takes one Map. Caller supplies workspaceId/projectId/resourceId/language and published scope.

- RagServiceClient: searchKnowledgeBase, indexPublishedContent, reindexDocument, getProcessingStatus, unpublishContent.
- VoiceAgentServiceClient: startOutboundCall, getCallDetails.
- NotificationServiceClient: send.

Implementations selected by app.integrations.mode=mock|rest (default rest). Mock requires demo/test profile. URLs/auth environment configured; REST clients use timeouts and sanitized exceptions. Mock results labeled mock=true. Do not write configuration owned by backend; coordinate exact properties.

## Progress

Implementation and native verification are complete. Frontend lint, 13 tests and production build pass. Backend verification packages the API with 24 passing tests. Schema and 22 API acceptance groups pass against PostgreSQL. See verification.md for evidence and remaining external validation.

Current accepted change: all persisted primary keys use PostgreSQL `BIGINT GENERATED BY DEFAULT AS IDENTITY`; JPA uses Java `Long` with `@GeneratedValue(strategy = GenerationType.IDENTITY)`. Foreign keys are BIGINT. JDBC creation obtains IDs through `RETURNING id`; callers never generate record IDs. API IDs are decimal strings for browser precision. Tenant authorization remains mandatory. This supersedes the original identifier choice everywhere, including migrations, integration contracts, tests and documentation. The verification database is empty, so the unreleased initial migration can be updated without migrating or deleting user data.

Final handoff packages the verified source and migration snapshot. External providers remain unverified until their actual contracts and credentials are configured. Docker image validation remains blocked by the local Docker engine; independent commands are documented for later execution.
