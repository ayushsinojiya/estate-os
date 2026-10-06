# CRM Record Lifecycle Actions Implementation Plan

> **For agentic workers:** Implement these tasks with test-first checks. Work in the shared checkout and preserve unrelated changes.

**Goal:** Add safe removal/cancellation actions to leads, completed conversations, site visits, and callbacks.

**Architecture:** PostgreSQL soft-deletion for leads and voice sessions; existing appointment/callback status transitions for cancellation. Spring services enforce tenant permissions and lifecycle guards; React pages provide confirmations and refresh visible queries.

**Tech Stack:** Spring Boot 3, PostgreSQL/Flyway, React/Vite, JUnit/Testcontainers, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-05-record-lifecycle-design.md`

## Global Constraints

- Keep numeric identity IDs and workspace scoping.
- No hard-delete cascade of CRM history.
- Do not claim a pending voice call is stopped by a UI-only status change.

## Review Focus

- Cross-workspace deletion must not expose or mutate another tenant's record.
- Pending calls and active visits must block lead removal.
- Deleted records must be absent from lists, related records, and dashboard metrics.
- Existing phone numbers on removed leads must not block a new lead.
- Cancellation must not run twice or after a terminal visit state.

## Tasks

### 1. Backend soft-removal

**Files:** `backend/src/main/resources/db/migration/V9__crm_soft_delete.sql`, `database/migrations/V9__crm_soft_delete.sql`, `backend/src/main/java/com/estraos/repository/TenantRepository.java`, `backend/src/main/java/com/estraos/service/EstateService.java`, `backend/src/main/java/com/estraos/controller/ApiController.java`, `backend/src/test/java/com/estraos/ApiIntegrationTest.java`.

- [x] Add failing integration tests for lead/call removal, permissions, lifecycle conflicts, lists, dashboard, and phone reuse.
- [x] Run focused integration tests and observe expected failures.
- [x] Add deleted-at columns and active contact uniqueness, workspace-scoped service/controller operations, read filtering, and dependent scheduling cleanup.
- [x] Run focused and full backend tests.

### 2. Lead and conversation controls

**Files:** `frontend/src/pages/Leads.tsx`, `frontend/src/pages/Calls.tsx`, `frontend/tests/leads.test.tsx`, `frontend/tests/calls.test.tsx`.

- [x] Add UI tests for visibility, confirmation, and success.
- [x] Run focused tests and observe expected failures.
- [x] Add manager-only remove actions with confirmations, disabled/busy states, query invalidation, and navigation.
- [x] Run focused frontend tests.

### 3. Scheduled-work cancellation controls

**Files:** `frontend/src/pages/SiteVisits.tsx`, `frontend/src/features/voice.tsx`, frontend tests for site visits and callbacks.

- [x] Add tests for active-only cancellation and confirmation.
- [x] Expose visit cancellation from list/schedule and confirm callback cancellation; preserve existing backend lifecycle endpoints.
- [x] Run focused frontend tests.

### 4. End-to-end verification

- [x] Run all backend and frontend tests, lint, build, and migration checks.
- [x] Validate representative actions in an isolated browser fixture at desktop width.
- [x] Check working-tree diff and report any verification gaps honestly.
