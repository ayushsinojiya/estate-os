# Table Date Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users filter all date-bearing tables by an inclusive local calendar date range, without breaking server pagination.

**Architecture:** Paginated lists send UTC range boundaries derived from the user's local dates; each backend list query filters its relevant timestamp before counting and paging. Embedded tables filter their already-loaded rows locally. A date-only mode of the existing custom calendar supplies consistent controls.

**Tech Stack:** React/TypeScript/Vitest, Spring Boot/PostgreSQL/JUnit, FastAPI/psycopg/pytest.

**Spec:** The user request in this task: “add date filter in every table.” Tables with no date-bearing record field cannot meaningfully be date-filtered, so leave those unchanged.

## Global Constraints

- Preserve existing visual design and custom date picker; no native browser date control.
- Reset server list pagination to page 1 when the range changes.
- Date range is inclusive in the browser's local calendar; backend receives exclusive UTC upper bound.
- Preserve unrelated dirty-worktree changes; do not commit them.

## Review Focus

- A record on the selected end date must remain visible, regardless of time of day.
- Empty and reversed ranges must not issue invalid server queries.
- Filtered pagination totals must reflect the full data set, not the current page.
- Detail tables with no date field must not show a misleading date filter.
- Calendar popovers must fit narrow viewports and dialogs.

---

### Task 1: Shared date controls and local tables

**Files:** `frontend/src/components/DateTimePicker.tsx`, `frontend/src/components/ui.tsx`, `frontend/src/components/DateRangeFilter.tsx`, `frontend/src/utils/dateFilter.ts`, `frontend/src/styles.css`, `frontend/tests/date-filters.test.tsx`

**Interfaces:** `DateRangeFilter({from,to,onFrom,onTo})`; `dateBounds(from,to)` returns ISO UTC boundaries; `DataTable` accepts `dateFilter?: boolean` (default true) and filters date-bearing rows when true.

- [x] Write tests for local date inclusion, clear, no-date table, and date-only calendar; run and observe failure.
- [x] Implement controls and filtering; run focused tests green.

### Task 2: Paginated CRM and managed-file lists

**Files:** `frontend/src/hooks/useList.ts`, list-page TSX files, `backend/src/main/java/com/estraos/repository/TenantRepository.java`, `backend/src/main/java/com/estraos/service/ManagedFileService.java`, `backend/src/main/java/com/estraos/controller/ApiController.java`, matching frontend/backend tests.

**Interfaces:** `dateFrom` and `dateTo` query parameters are UTC instants, lower-inclusive and upper-exclusive. `useList` owns local-date state, resets page, and supplies `Filters` props.

- [x] Write frontend and backend tests for filtering, date bounds, count, and page reset; run and observe failure.
- [x] Implement backend predicates and frontend query controls, including visit scheduled date; run focused tests green.

### Task 3: Knowledge-source list and full verification

**Files:** `frontend/src/pages/Files.tsx`, `backend/src/main/java/com/estraos/{controller/RagIngestionController,service/RagIngestionService}.java`, `rag/rag_service/{api,store}.py`, matching tests.

**Interfaces:** Same `dateFrom`/`dateTo` UTC-instants contract as Task 2.

- [x] Write tests for RAG source list filtering; run and observe failure.
- [x] Forward and apply filters, then run focused tests green.
- [x] Run complete frontend/backend/RAG test suites, lint, build, and browser verification at desktop and mobile widths.
