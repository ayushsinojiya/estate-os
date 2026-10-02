# Website Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the relevant items in the user's 20-item website checklist to the EstraOS app and verify the result in a browser.

**Architecture:** Keep the existing React Router layout and shared components. Add small shared metadata/contact helpers, improve the unknown-route experience, and correct responsive styles based on measured browser overflow. Avoid duplicating working menu, toast, and error behavior.

**Tech Stack:** React 19, React Router 7, TypeScript, Vite, Tailwind/CSS, Vitest, browser inspection.

**Spec:** `docs/website-quality-audit.md`

## Global Constraints

- Apply changes in `D:\my hope\real-estate-ai-mvp`; preserve unrelated worktree edits.
- Keep hidden sidebar destinations hidden and their existing routes available.
- Preserve existing design colors and icon sizes.
- Do not introduce new credentials, fabricated support links, or image transformations for external media.

## Review Focus

- Unknown routes while signed in: show a 404 page with a working dashboard link.
- Lead phone or email absent: show the existing fallback without creating an empty contact link.
- Narrow workspace header: menu, workspace switcher, alerts, and profile remain reachable.
- Wide data tables on mobile: scrolling stays within the table panel, not the whole page.
- Network failures during writes: existing error feedback remains visible.

---

### Task 1: Metadata and identity

**Files:** `frontend/index.html`, `frontend/public/favicon.svg`, `frontend/src/hooks/usePageMetadata.ts`, `frontend/src/components/ui.tsx`, `frontend/src/pages/Login.tsx`, `frontend/src/layouts/AppLayout.tsx`.

**Interfaces:** `usePageMetadata(title: string, description?: string): void` updates title and the existing description tag. `PageHeader` calls it for routed content.

- [x] Add a branded vector favicon and HTML reference.
- [x] Make route titles and descriptions follow page headers; set login metadata separately.
- [x] Make login branding link to the home route and add the current footer year.
- [x] Verify titles/favicon/footer in the browser and with component tests.

### Task 2: Routes and contact links

**Files:** `frontend/src/routes/App.tsx`, `frontend/src/pages/NotFound.tsx`, `frontend/src/components/ContactLink.tsx`, `frontend/src/components/ui.tsx`, `frontend/src/pages/Leads.tsx`, `frontend/src/pages/Settings.tsx`.

**Interfaces:** `ContactLink` accepts `kind: 'phone' | 'email'` and a contact value; `NotFound` renders the route fallback.

- [x] Replace the generic unknown-route state with an actionable 404 page.
- [x] Link actual lead, member, and profile contact values with safe `tel:` and `mailto:` links.
- [x] Preserve navigation and form behavior; add focused tests for 404 and contact links.

### Task 3: Responsive and interaction verification

**Files:** `frontend/src/styles.css`, `frontend/src/pages/Projects.tsx`, relevant frontend tests.

- [x] Audit 320, 768, 1024, and 1440 pixel browser widths on login, dashboard, a table page, and a detail page.
- [x] Fix measured page overflow and inaccessible controls; retain internal scrolling for wide tables.
- [x] Lazy-load external project images and decode asynchronously.
- [x] Exercise navigation, a primary action, a success state, and a recoverable error state.
- [x] Run frontend lint, tests, build, and final browser checks.
