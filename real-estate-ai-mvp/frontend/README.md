# EstraOS frontend

React, TypeScript, Tailwind CSS and Vite workspace for managing real-estate inquiries through qualification, property recommendations, site visits and human handover.

## Run locally

Use Node.js 22.13 or newer and npm. Vite 6 also runs on Node 20, but current lint dependencies require at least 20.19.

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Open the URL printed by Vite (normally http://localhost:5173). Start the independent backend first. `VITE_API_URL` defaults to `/api/v1`. The local Vite proxy forwards `/api` to `API_PROXY_TARGET`, default `http://localhost:8080`. Set `VITE_API_URL=https://your-api.example/api/v1` when the browser should contact the backend directly, and allow the frontend origin in backend CORS configuration. All VITE variables are public build-time values: never include credentials.

Demo accounts are `admin@estraos.demo`, `manager@estraos.demo` and `agent@estraos.demo`. The backend administrator supplies their demo password through `DEMO_PASSWORD`; no password is shipped in this project.

## Verify and build

```sh
npm run lint
npm test
npm run build
npm audit --omit=dev
```

Tests exercise authentication, protected routes, project results and role visibility, lead creation/editing, site-visit booking, form validation and loading/error handling against mocked HTTP responses. The production bundle is in `dist/`.

## Docker

```sh
docker build --build-arg VITE_API_URL=http://localhost:8080/api/v1 -t estraos-frontend .
docker run --rm -p 3000:8080 estraos-frontend
```

The backend URL must be reachable by the user's browser, not only by Docker networking. For same-origin production hosting, leave `VITE_API_URL=/api/v1` and configure your external reverse proxy to route `/api` to the backend. The included unprivileged Nginx serves static assets and SPA routes; it does not proxy the API. Frontend port is 8080 inside the container.

## Architecture and behavior

`src/api` owns the bearer-token and workspace HTTP client. `src/hooks` owns session/workspace context and React Query access. `src/features` contains workflow field definitions. `src/components` provides accessible dialogs, forms, tables and feedback states. `src/pages`, `src/layouts`, and `src/routes` organize the screens. `tests` contains frontend tests and their setup, separate from production source.

IDs are opaque decimal strings in browser state and request bodies, preserving PostgreSQL BIGINT precision. Workspace IDs are headers and every request is still checked for membership by the backend. Switching workspace clears the query cache. Tokens are stored in per-tab session storage, verified against `/auth/me` on startup, removed on logout and cleared on 401. Protect the deployed application with HTTPS and a suitable CSP; session storage is accessible to scripts running in the same origin.

ADMIN and MANAGER can manage projects, inventory and property documents and inspect audit events. All workspace roles can manage leads, visits, calls and handovers. Assignment selectors contain real-estate agents only. Role visibility complements backend checks.

Original PDFs are registered using metadata and an existing storage reference; the external storage service owns original file bytes. Content editing, publishing, version history and re-index requests are persisted through the backend. Outbound calling asks for confirmation. Cancelling a visit, deactivating a project and publishing/unpublishing content use confirmation dialogs. Notifications record provider outcomes; mock delivery does not mean a real message was sent.

Currency is INR, areas are square feet, and appointment times are displayed in the browser's local timezone and sent as UTC. English interface text and English/Hindi/Gujarati/Marathi content-language labels are supported; a full translated interface is outside this MVP. For the first MVP, dropdowns load up to 100 matching records; very large workspaces should add server-backed searchable selectors. Lists use server pagination and filters. There is no agent configuration, buying, payment or legal transaction screen.
