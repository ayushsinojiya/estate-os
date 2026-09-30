# Architecture

EstraOS covers inquiry through qualification, property recommendations, site visits, and human-agent handover. Buying, contracts, payments, and legal processing remain with the human agent.

The React application calls a versioned Spring Boot API. PostgreSQL owns business records, relationships, histories, and delivery state. Flyway applies forward-only migrations at startup. Existing AI and delivery services are accessed only through replaceable Java interfaces. No embedding storage or voice-agent internals are included.

## Tenant and authorization boundary

Users authenticate by email/password and receive an expiring JWT. Each workspace request carries a workspace header. The backend verifies the authenticated user's membership, derives the role for that workspace, and scopes resource queries. A supplied workspace or resource identifier is never sufficient authority by itself. ADMIN and MANAGER may administer inventory and published knowledge; all three business roles may operate leads and appointments. Audit access is restricted.

Tenant-owned rows carry workspace_id. Related project records also carry project_id. Compound ownership constraints and service validation prevent cross-tenant relationships. Numeric identifiers are not access controls. API DTOs separate editable fields from identity, ownership, and audit metadata. Password hashes never enter response DTOs.

## Workflow

1. An operator creates or updates a lead's contact details and structured requirements.
2. The voice adapter can initiate a call and synchronize transcript, outcome, summary, and extracted requirements. Mock results are labeled when demo mode is enabled.
3. Structured inventory queries find currently available units matching budget, location, type, BHK and area. Published document knowledge is obtained through the scoped RAG adapter.
4. Selected recommendations are recorded against the lead. Booking validates the unit again and prevents overlapping appointments.
5. A handover records assignment and the relevant lead, call, recommendation and appointment context. Notifications and audit history preserve the operational trail.

Persisted reminders use a due timestamp and a scheduled state. A small polling worker takes row locks with `SKIP LOCKED`, so multiple API replicas do not concurrently dispatch the same row. It sends a stable notification-specific idempotency key, then records the provider outcome. Provider failures become explicit failed deliveries rather than blind retries. Real delivery callbacks and provider-side idempotency semantics must be verified when connecting the gateway.

## Knowledge lifecycle

Register an original PDF's metadata and storage reference, then review/edit human-readable text. Content versions preserve prior edits. Publishing enables indexing through the existing RAG service. Draft or unpublished content must not be retrieved as production knowledge. Indexing/processing status and provider errors are surfaced separately from the human-readable record. English, Hindi, Gujarati and Marathi are stored as language codes; semantic behavior belongs to the external RAG service.

The application does not assume that SQL keyword search is multilingual semantic search. Original file bytes remain in configured storage; registration does not itself upload bytes to that provider.

## Runtime boundaries

The frontend and backend have independent dependency manifests, tests, builds, environment examples and Dockerfiles. PostgreSQL and external service networking are operator-managed. Mock mode is an explicit development/test choice; production expects reachable configured services. Secrets belong in runtime environment or a secret manager, never the distributable archive.

## Selected references

- [Spring Boot 3.5 system requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java/Maven compatibility.
- [Tailwind installation](https://tailwindcss.com/docs/installation/using-vite): build integration.
- [PostgreSQL range constraints](https://www.postgresql.org/docs/current/rangetypes.html#RANGETYPES-CONSTRAINT): database support for excluding overlapping bookings.

See integration.md for provisional external contracts and setup.md for runtime configuration.
