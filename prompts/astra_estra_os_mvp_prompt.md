## EXECUTION STRATEGY — MANDATORY

Do not attempt the entire project blindly in one uninterrupted implementation pass.

First:
1. Read the complete prompt.
2. Inspect the workspace.
3. Create an implementation plan.
4. Identify missing information and external integration blockers.
5. Create a task checklist with acceptance criteria.
6. Start implementation only after the plan is complete.

Execute the project in these phases:

Phase 1 — Workspace inspection and architecture
Phase 2 — Backend foundation, database, authentication, authorization, tenancy
Phase 3 — Frontend foundation, routing, layout, authentication, role-based UI
Phase 4 — Real-estate workflows and API integration
Phase 5 — RAG and Voice Agent integration adapters
Phase 6 — Dockerfiles, environment examples, migrations, and documentation
Phase 7 — Tests, linting, compilation, builds, and migration validation
Phase 8 — Fix all discovered issues
Phase 9 — Final security and tenant-isolation review
Phase 10 — Create and validate the final source-code ZIP

After every phase:
- Run the relevant checks.
- Fix errors before moving forward.
- Update the checklist.
- Record blockers and assumptions.
- Do not rewrite working code unnecessarily.
- Do not stop after generating files without validating them.

If the task reaches a usage, context, tool, or time limit:
- Preserve all completed work in the workspace.
- Write a clear progress report.
- Record the exact next task.
- Do not claim the project is complete.

## SUB-AGENT RULES

Sub-agents may work in parallel only when their changes do not conflict.

Suggested assignments:

1. Backend:
   - Spring Boot
   - PostgreSQL
   - JWT
   - roles
   - workspace/project tenant isolation
   - APIs
   - backend tests

2. Frontend:
   - React
   - Tailwind
   - routing
   - authentication screens
   - dashboards
   - lead/property/site-visit flows

3. Integration and infrastructure:
   - RAG adapter
   - Voice Agent adapter
   - environment variables
   - Dockerfiles
   - API documentation

4. QA and review:
   - inspect requirements
   - run tests/builds
   - check authorization and tenant isolation
   - identify missing features
   - do not make broad unrelated rewrites

Every sub-agent must:
- Read existing files before editing.
- Reuse existing dependencies and abstractions.
- Avoid changing another agent’s area without coordination.
- Report changed files, tests run, failures, and remaining work.


# Role

Act as a senior product architect, UX designer, frontend engineer, backend engineer, database engineer, QA engineer, and DevOps engineer.

You have maximum autonomy. Use your reasoning and engineering judgment to complete the MVP end-to-end without asking me follow-up questions after this prompt. Do not guess carelessly. If something is not specified, choose the most practical, secure, modern, maintainable, and MVP-appropriate solution yourself.

Your goal is to deliver a **working, runnable, production-quality MVP**, not just mockups, pseudo-code, incomplete files, or architecture suggestions.

---

# Product

Build a multi-tenant real-estate AI assistant platform.

The platform helps real-estate businesses manage the initial customer journey:

```text
Customer inquiry
→ AI voice conversation
→ Understand customer requirements
→ Capture and qualify lead
→ Recommend suitable properties
→ Book a site visit
→ Handover to human real-estate agent
```

The application ends after the qualified lead and site-visit handover.

The application must not handle the final property-buying process.

---

# Important scope restriction

The AI RAG service and AI Voice Agent are already developed.

Do **not** create, rebuild, or redesign the RAG engine or Voice Agent.

Do not create AI-agent configuration screens.

Do not create prompt-management screens for AI agents.

Do not create voice-provider management screens.

Do not implement the internal AI voice logic.

Instead, create clean integration points and connect the main application to the existing services through configurable REST APIs.

If the existing service contracts are unavailable, create a clean adapter interface and a clearly marked mock implementation so the application remains runnable. Keep the integration isolated and easy to replace.

---

# Technology stack

## Frontend

* React
* Tailwind CSS
* Modern component architecture
* Responsive design
* Accessible UI
* Clean state management
* API service layer
* Form validation
* Loading, empty, success, and error states

## Backend

* Java
* Spring Boot
* Spring Web
* Spring Data JPA
* Bean Validation
* Spring Security
* JWT authentication
* REST APIs
* OpenAPI/Swagger
* Global exception handling
* Proper logging
* Transaction management

## Database

* PostgreSQL
* Flyway or Liquibase migrations
* Proper foreign keys
* Indexes
* Constraints
* Audit fields
* Multi-tenant data isolation

## Existing services

Integrate with:

1. Existing RAG service
2. Existing Voice Agent service

Use environment variables for all external service URLs, credentials, and configuration.

---

# Repository structure

Create a clean repository with separate projects:

```text
frontend/
backend/
```

Use a maintainable structure.

Frontend should include:

```text
components/
pages/
layouts/
routes/
hooks/
services/
api/
types/
utils/
features/
```

Backend should include:

```text
config/
security/
controller/
service/
repository/
entity/
dto/
mapper/
exception/
integration/
audit/
```

Use feature-based organization where it improves maintainability.

---

# Authentication and authorization

Implement email/password authentication with JWT.

Required roles:

* ADMIN
* MANAGER
* REAL_ESTATE_AGENT

Implement:

* Login
* Logout behavior on frontend
* Password hashing
* JWT authentication
* Protected routes
* Role-based API authorization
* Role-based UI visibility
* Current-user endpoint
* Seeded demo users
* Secure password handling
* Unauthorized and forbidden responses

Do not store raw passwords.

---

# Multi-tenancy

The application must support multiple workspaces/tenants.

Every tenant-owned table must include:

```text
workspace_id
```

Project-specific records should also include:

```text
project_id
```

Always validate workspace access on the backend.

Never trust `workspace_id` supplied by the frontend without checking the authenticated user’s membership.

Prevent cross-workspace data leakage in:

* Projects
* Units
* Leads
* Calls
* Site visits
* Documents
* Property content
* Audit logs
* Analytics

Use a clear and consistent tenant-isolation strategy.

---

# MVP features

Implement all of the following.

## 1. Dashboard

Create a modern dashboard showing:

* Total leads
* New leads
* Qualified leads
* Total projects
* Available units
* Site visits booked
* Upcoming site visits
* Calls handled
* Lead conversion summary
* Recent activities
* Upcoming follow-ups

Use realistic seeded data.

Do not use fake metrics that are presented as real production data. Clearly identify demo data where applicable.

---

## 2. Project management

Implement:

* Project list
* Search
* Filters
* Sorting
* Pagination
* Create project
* View project
* Edit project
* Activate/deactivate project
* Project details
* Project location
* Project description
* Builder/developer information
* Possession information
* Project amenities
* Project images/media metadata
* Project documents
* Project status

Suggested project statuses:

* ACTIVE
* INACTIVE
* COMPLETED
* ARCHIVED

---

## 3. Property and unit inventory

Implement:

* Buildings/towers
* Floors
* Unit types
* Units
* BHK/type
* Area
* Floor
* Facing
* Price
* Availability
* Unit status history
* Search and filtering
* Inventory summary
* Create/edit unit
* Import inventory from CSV or Excel if practical
* Prevent invalid duplicate unit numbers within the same project/building

Suggested unit statuses:

* AVAILABLE
* RESERVED
* SOLD
* BLOCKED
* UNAVAILABLE

The recommendation and booking flow must check current unit availability.

---

## 4. Property knowledge management

The same property PDF must support both:

1. Original document storage
2. Human-readable and editable content
3. Embeddings managed by the existing RAG service

Implement:

* Upload property PDF metadata
* Store file metadata and storage reference
* Document list
* Document details
* Processing status
* Human-readable content view
* Editable content view
* Draft/published state
* Content version history
* Language field
* Source document reference
* Page/section reference where available
* Re-index request integration with the existing RAG service
* Processing errors
* Publish/unpublish workflow

Do not implement the embedding engine.

Create an integration interface such as:

```text
RagServiceClient
```

Support operations such as:

```text
searchKnowledgeBase(...)
indexPublishedContent(...)
reindexDocument(...)
getProcessingStatus(...)
```

Use mock adapters only when real endpoints are unavailable.

Only published content should be used for production retrieval.

---

## 5. Multilingual support

Support:

* English
* Hindi
* Gujarati
* Marathi

The system must store the content language.

The RAG integration must support multilingual semantic search.

The backend should pass language and workspace/project context to the RAG service when supported.

Do not assume that PostgreSQL keyword search is automatically multilingual. Keep language-specific search behavior inside the RAG integration layer.

The UI should support language labels and localized user-facing text where practical.

---

## 6. Lead management

Implement:

* Lead list
* Search
* Filters
* Sorting
* Pagination
* Create lead
* Edit lead
* Lead details
* Lead status
* Lead source
* Lead assignment
* Lead tags
* Lead notes
* Lead activity timeline
* Lead preferences
* Customer requirements
* Call history
* Recommended properties
* Site-visit history
* Handover status

Capture:

* Name
* Phone
* Email
* Preferred language
* Buying/renting intent
* Budget range
* Preferred location
* Property type
* BHK
* Area preference
* Possession timeline
* Purpose
* Urgency
* Notes

Suggested lead statuses:

* NEW
* CONTACTED
* QUALIFIED
* VISIT_PLANNED
* VISIT_COMPLETED
* HANDED_OVER
* NOT_INTERESTED
* LOST

Prevent duplicate leads where practical using phone/email matching within the same workspace.

---

## 7. AI voice integration

Do not build the Voice Agent itself.

Integrate with the existing Voice Agent through an adapter such as:

```text
VoiceAgentServiceClient
```

Support configurable operations such as:

* Start outbound call
* Get call status
* Get call details
* Get transcript
* Get call summary
* Get detected customer requirements
* Get recommended properties if supported
* Transfer/handover status
* Callback status

Create a clean UI based on the most useful MVP experience. Prefer:

* Call history
* Call details
* Transcript
* AI summary
* Extracted customer requirements
* Call outcome
* Lead association
* Handover action

If the existing Voice Agent supports starting calls, expose that action.

If the service contract is unavailable, isolate the mock implementation behind the adapter and document exactly where the real API must be connected.

Do not create AI-agent management screens.

---

## 8. Property recommendation

Implement a recommendation workflow that:

* Accepts customer requirements
* Finds matching projects/units
* Filters by budget
* Filters by location
* Filters by property type
* Filters by BHK
* Filters by area
* Filters by availability
* Shows matching properties
* Shows why each property matches
* Allows the agent to select properties
* Records which properties were suggested to the lead

Use normal PostgreSQL queries for structured property/unit data.

Use the existing RAG service for document-based knowledge such as:

* Amenities
* Payment plans
* Project descriptions
* Possession details
* FAQs
* Brochure information

Do not allow the LLM or frontend to directly query unrestricted database tables.

---

## 9. Site-visit booking

Implement:

* Site-visit list
* Calendar or schedule view
* Create site visit
* Select lead
* Select project
* Select assigned real-estate agent
* Select date and time
* Confirm booking
* Reschedule
* Cancel
* Mark completed
* Mark no-show
* Prevent double booking
* Upcoming visits
* Visit details
* Customer confirmation status
* Agent notification status

Suggested statuses:

* REQUESTED
* CONFIRMED
* RESCHEDULED
* CANCELLED
* COMPLETED
* NO_SHOW

Implement backend validation for conflicting bookings.

---

## 10. Human-agent handover

Create a handover workflow containing:

* Lead details
* Customer requirements
* Call summary
* Transcript reference
* Recommended properties
* Selected property/project
* Site-visit details
* Customer questions
* Agent assignment
* Handover status
* Handover notes
* Handover timestamp

Suggested statuses:

* PENDING
* ASSIGNED
* ACCEPTED
* COMPLETED

The app should clearly communicate that the human real-estate agent handles all later buying and legal activities.

---

## 11. Notifications

Implement the notification architecture and MVP UI for:

* Site-visit confirmation
* Site-visit reminder
* Rescheduling
* Cancellation
* Agent assignment
* Handover notification
* Failed call
* Callback reminder

External SMS, WhatsApp, or email delivery should be integrated through adapters.

If providers are not available, create a mock notification provider and store delivery status.

---

## 12. Audit logs

Track important events:

* Login
* Logout
* Project creation/update
* Unit creation/update
* Lead creation/update
* Lead assignment
* Document upload
* Content edit
* Content publish
* Site-visit creation/update/cancellation
* Agent handover
* External service failures

Audit logs must include:

* Workspace
* User
* Action
* Entity type
* Entity ID
* Timestamp
* Metadata
* IP address if safely available

---

# Required database tables

Create migrations for the core MVP tables.

At minimum include:

```text
workspaces
users
workspace_members
roles
permissions
role_permissions

projects
project_locations
amenities
project_amenities
buildings
floors
unit_types
units
unit_status_history
unit_prices

leads
lead_contacts
lead_sources
lead_status_history
lead_assignments
lead_preferences
lead_tags
lead_notes
lead_activities

property_documents
property_document_versions
property_content
property_content_versions

voice_sessions
voice_session_events
voice_transcripts
voice_summaries
voice_session_requirements

appointments
appointment_participants
appointment_status_history

handover_records
notifications
notification_deliveries

files
audit_logs
api_request_logs
outbox_events
idempotency_keys
```

Use UUID primary keys.

Use UTC timestamps.

Use created/updated audit fields.

Add appropriate indexes for:

* `workspace_id`
* `project_id`
* `status`
* `phone`
* `email`
* `scheduled_at`
* common search fields
* foreign keys

Do not create RAG embedding tables unless required by the existing RAG service. The existing RAG service owns embedding storage and retrieval.

---

# API requirements

Create complete Spring Boot REST APIs for the MVP.

Include:

* Authentication APIs
* Current-user API
* Workspace APIs
* Project APIs
* Building/floor/unit APIs
* Amenity APIs
* Lead APIs
* Property document/content APIs
* Voice integration APIs
* Recommendation APIs
* Site-visit APIs
* Handover APIs
* Notification APIs
* Dashboard APIs
* Audit APIs

Use:

* DTOs instead of exposing entities
* Request validation
* Consistent response format
* Proper HTTP status codes
* Pagination
* Sorting
* Filtering
* Global error handling
* API versioning such as `/api/v1`
* OpenAPI documentation

Use a consistent error response:

```json
{
  "timestamp": "...",
  "status": 400,
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "details": {}
}
```

---

# Frontend UI requirements

Build a modern SaaS application with:

* Responsive sidebar navigation
* Top navigation
* Workspace selector
* User menu
* Breadcrumbs
* Dashboard cards
* Data tables
* Filters
* Search
* Pagination
* Detail drawers or detail pages
* Forms
* Modal confirmations
* Toast notifications
* Skeleton loading
* Empty states
* Error states
* Responsive mobile layout
* Accessible keyboard navigation
* Clear focus states
* Confirmation for destructive actions

Use a modern, professional real-estate SaaS design.

Preferred visual direction:

* Clean
* Premium
* Minimal
* Trustworthy
* Professional
* Spacious
* Strong typography
* Neutral background
* One consistent accent color
* Semantic colors for success, warning, and error
* No excessive gradients
* No unnecessary animations
* No visual clutter

Use standard design-system spacing, typography, border radius, shadows, and component states.

Do not create an overly complicated dashboard.

Prioritize usability and clear workflows over decoration.

---

# Frontend pages

Create at least:

```text
/login
/dashboard
/projects
/projects/:id
/projects/:id/units
/projects/:id/documents
/leads
/leads/:id
/calls
/calls/:id
/recommendations
/site-visits
/site-visits/:id
/handovers
/notifications
/settings/profile
```

Do not create AI-agent configuration pages.

---

# Integration configuration

Use environment variables such as:

```text
DATABASE_URL
JWT_SECRET
RAG_SERVICE_URL
VOICE_AGENT_SERVICE_URL
NOTIFICATION_SERVICE_URL
FILE_STORAGE_URL
```

Never hardcode secrets.

Provide `.env.example` files.

Clearly document the expected API contracts for the RAG and Voice Agent services.

---

# Seed data

Provide seed data for:

* One demo workspace
* Admin user
* Manager user
* Real-estate agent user
* Several projects
* Buildings
* Floors
* Unit types
* Available and unavailable units
* Amenities
* Leads
* Calls
* Site visits
* Notifications

Clearly document demo credentials without using real passwords or secrets.

---

# Testing

Create and run:

## Backend tests

* Authentication tests
* Authorization tests
* Workspace-isolation tests
* Project tests
* Unit availability tests
* Lead tests
* Site-visit conflict tests
* Handover tests
* Validation tests
* Integration adapter tests

## Frontend tests

* Login flow
* Protected routes
* Project list
* Lead creation/editing
* Site-visit booking
* Form validation
* Error and loading states

Fix all compilation, lint, test, and runtime errors autonomously.

---

# Quality requirements

Do not:

* Leave TODOs for core functionality
* Use placeholder pages for required features
* Use hardcoded production secrets
* Expose database entities directly
* Trust tenant IDs from the frontend
* Allow cross-workspace access
* Create AI-agent configuration functionality
* Rebuild the existing RAG or Voice Agent
* Claim external integrations work if their contracts are unavailable

When an external integration is unavailable:

1. Create an interface.
2. Create a mock adapter.
3. Add configuration for the real adapter.
4. Clearly document the replacement point.
5. Keep the application runnable.

---

# Execution instructions

Work independently and complete the entire MVP.

You should:

1. Inspect the existing repository if one is provided.
2. Determine the current project structure.
3. Preserve useful existing code.
4. Create missing frontend and backend files.
5. Create database migrations.
6. Create seed data.
7. Implement APIs.
8. Implement frontend pages.
9. Implement external-service adapters.
10. Add tests.
11. Run builds and tests.
12. Fix errors.
13. Verify the complete user flow.
14. Provide setup instructions.
15. Provide integration instructions for the existing RAG and Voice Agent.

Do not stop after generating a plan.

Do not ask me to choose between multiple technical options.

Make sensible decisions autonomously and continue until the MVP is runnable.

---

# Final acceptance flow

The following flow must work:

```text
Login
→ Open dashboard
→ View projects
→ View available units
→ Upload or view property document
→ Edit and publish property content
→ View or create lead
→ View customer requirements
→ View call transcript and summary
→ Recommend matching properties
→ Book site visit
→ Assign human real-estate agent
→ Create handover record
→ Display confirmation and activity history
```

At the end, provide:

* Final folder structure
* Setup commands
* Environment variables
* Database migration instructions
* Seed credentials
* API documentation URL
* Test commands
* RAG integration contract
* Voice Agent integration contract
* Known limitations
* Exact next steps only for unavailable external credentials or API contracts

Use maximum engineering effort, strong reasoning, secure defaults, optimized implementation, and modern UI standards. Complete the work using your own capabilities without unnecessary questions.

# FINAL EXECUTION, RESEARCH, TOKEN OPTIMIZATION, AND ZIP DELIVERY INSTRUCTIONS

## 1. External research and references

Use external websites and official documentation whenever research materially
improves the implementation.

Prioritize primary and reliable sources, including:

- Official React documentation
- Official Tailwind CSS documentation
- Official Spring Boot documentation
- Official PostgreSQL documentation
- Official Docker documentation
- Official JWT and Spring Security documentation
- Official OpenAPI documentation
- Official accessibility guidelines
- Official documentation for the existing RAG service
- Official documentation for the existing Voice Agent service
- Reputable modern SaaS UI and UX references
- Official documentation for any library or integration used

Use external references to improve:

- Application architecture
- React and Tailwind implementation
- Spring Boot API design
- PostgreSQL schema and indexing
- Authentication and authorization
- Multi-tenant security
- API integration
- Accessibility
- Responsive UI
- Performance
- Testing
- Docker configuration
- Error handling
- Security practices

Research rules:

1. Prefer official and primary sources.
2. Verify important or version-sensitive information.
3. Do not blindly copy code, designs, branding, or proprietary content.
4. Adapt references to this application’s requirements.
5. Do not spend tokens researching unrelated topics.
6. Do not repeatedly research the same decision.
7. Record important technical decisions briefly in the documentation.
8. If web access is unavailable, continue using reliable existing knowledge.
9. Do not claim that external research was performed unless it was actually performed.
10. Use the existing repository and existing dependencies as the primary source of truth.

Do not rebuild the existing RAG or Voice Agent internals. Research only the
integration contracts, authentication, request formats, response formats, and
error-handling requirements needed to connect them to this application.

---

## 2. Important token optimization rules

Optimize token usage without reducing implementation quality.

Follow these rules:

1. Inspect the workspace before making assumptions.
2. Read only relevant files.
3. Do not repeatedly reread unchanged files.
4. Use targeted searches instead of scanning the entire workspace repeatedly.
5. Reuse existing components, utilities, services, dependencies, and patterns.
6. Do not create duplicate components, DTOs, hooks, services, utilities, or APIs.
7. Keep the architecture simple and appropriate for an MVP.
8. Avoid unnecessary abstractions and overengineering.
9. Do not create unnecessary microservices.
10. Do not generate unnecessary documentation or boilerplate.
11. Do not rebuild the RAG or Voice Agent internals.
12. Keep RAG and Voice Agent integration behind clean adapter interfaces.
13. Batch related file changes when safe.
14. Work in logical feature groups.
15. Run focused tests after each major feature group.
16. Run the complete test suite and production builds before completion.
17. Fix errors directly instead of only reporting them.
18. Do not stop after creating a plan; continue implementation.
19. Do not ask for confirmation for normal technical decisions.
20. Make sensible decisions when requirements are unspecified.
21. Ask only before destructive actions, irreversible database operations,
    production actions, secret changes, or actions outside the workspace.
22. Avoid unnecessary dependency additions.
23. Prefer stable, well-supported libraries already present in the project.
24. Keep API responses, logs, and generated documentation concise.
25. Do not generate duplicate implementations for the same feature.
26. Do not create mock functionality when the real integration contract is known.
27. Use mocks or local stubs only when external services are unavailable and
    clearly label them as development-only.
28. Keep the final response concise.

At the end of each implementation phase, report only:

- What was completed
- Files changed
- Tests/builds executed
- Failures or blockers
- Next implementation action

---

## 3. Web research configuration

Web research is enabled when available, but must be selective and purposeful.

Use web research for:

- Current framework best practices
- Version-sensitive configuration
- Security recommendations
- API and integration documentation
- Accessibility guidance
- Docker configuration
- PostgreSQL and migration practices
- Existing RAG service integration
- Existing Voice Agent integration
- Modern SaaS UI references

Research priority:

1. Official documentation
2. Primary technical sources
3. Reputable engineering documentation
4. Reputable UI/UX references
5. Community sources only when primary sources are insufficient

Do not use web research for:

- Generic explanations that are not needed for implementation
- Repeatedly verifying unchanged information
- Unrelated libraries or frameworks
- Unnecessary design inspiration
- Features outside the approved MVP scope
- Rebuilding existing AI-agent internals

When research is used:

1. Apply the result directly to the implementation.
2. Keep the explanation short.
3. Document only decisions that affect maintainability or setup.
4. Do not include unnecessary copied content.
5. Do not claim a source was checked if web access was unavailable.

If a technical choice is uncertain, choose the simplest stable option that
fits the current React, Tailwind, Spring Boot, PostgreSQL, Docker, RAG, and
Voice Agent architecture.

---

## 4. Full source-code ZIP delivery — mandatory

I will not provide GitHub, GitLab, repository, branch, commit, or Git access.

At the end of the task, deliver the complete source code as a clean downloadable
ZIP archive, similar to a source-code ZIP downloaded from GitHub.

The ZIP must contain the complete application source code and configuration.
I will configure Docker, PostgreSQL, environment variables, and external services
myself.

Do not require Git access.
Do not create Git branches.
Do not create Git commits.
Do not push code anywhere.
Do not require ASTRA access after the ZIP is delivered.

### Required ZIP structure

Create a structure similar to:

real-estate-ai-mvp.zip
└── real-estate-ai-mvp/
    ├── frontend/
    │   ├── src/
    │   ├── public/
    │   ├── package.json
    │   ├── package-lock.json or yarn.lock
    │   ├── Dockerfile
    │   ├── .dockerignore
    │   ├── .env.example
    │   └── README.md
    │
    ├── backend/
    │   ├── src/
    │   ├── pom.xml
    │   ├── Dockerfile
    │   ├── .dockerignore
    │   ├── .env.example
    │   └── README.md
    │
    ├── database/
    │   ├── migrations/
    │   ├── seed/
    │   └── README.md
    │
    ├── docs/
    │   ├── architecture.md
    │   ├── api.md
    │   ├── setup.md
    │   └── integration.md
    │
    └── README.md

The exact structure may be improved when necessary, but frontend and backend
must remain independent and understandable repositories/folders.

### Frontend repository requirements

The frontend folder must contain:

- Complete React source code
- Tailwind CSS configuration
- package.json
- Lock file
- Build configuration
- Tests
- Environment example
- Dockerfile
- .dockerignore
- README.md
- Configurable backend API base URL

### Backend repository requirements

The backend folder must contain:

- Complete Spring Boot source code
- pom.xml
- Application configuration
- REST APIs
- DTOs
- Validation
- Exception handling
- Security configuration
- Database migration configuration
- Tests
- Environment example
- Dockerfile
- .dockerignore
- README.md
- Configurable RAG service integration
- Configurable Voice Agent integration

### Docker configuration requirements

Provide Docker configuration in the appropriate repository.

For the frontend, include:

- Frontend Dockerfile
- .dockerignore
- Required environment configuration
- Build and run instructions
- Configurable backend API URL

For the backend, include:

- Backend Dockerfile
- .dockerignore
- Required environment configuration
- PostgreSQL connection configuration
- Migration configuration
- RAG service configuration
- Voice Agent service configuration

I will manage Docker networking, PostgreSQL startup, environment variables,
service URLs, and external service credentials myself.

Do not require a root-level Docker Compose setup unless it is genuinely useful.
Do not force a universal one-command installer.

If Docker Compose is included, make it optional and document its purpose clearly.

### Files that must not be included

Do not include:

- node_modules/
- target/
- build/
- dist/
- coverage/
- logs/
- caches
- IDE metadata
- local database files
- real .env files
- API keys
- passwords
- JWT secrets
- private keys
- production credentials
- Git metadata
- .git/ directories
- temporary files
- ASTRA-specific internal files

Use relative paths only.

Do not use:

- Absolute paths
- Original developer usernames
- Internal workspace paths
- Machine-specific configuration
- Hidden dependencies outside the extracted project
- References to unavailable Git repositories

The ZIP must be movable to another suitable folder or computer after extraction.

---

## 5. Environment configuration

Create only safe example configuration files:

- .env.example
- frontend/.env.example
- backend/.env.example

Document every required environment variable, including:

- Frontend backend API URL
- PostgreSQL URL
- Database username
- Database password
- JWT secret
- RAG service URL
- RAG authentication configuration
- Voice Agent service URL
- Voice Agent authentication configuration
- File storage configuration
- Email/notification configuration, if applicable
- CORS configuration
- Allowed frontend origins

Never include real credentials.

Use clear placeholder values and explain how each variable is used.

The application must fail with a clear and useful error when a required variable
is missing or invalid.

---

## 6. Database requirements

Include:

- PostgreSQL schema
- Versioned migrations
- Development seed data
- Required indexes
- Foreign keys
- Unique constraints
- Tenant-isolation constraints where practical
- Migration instructions
- Development reset instructions

Do not automatically delete or reset databases during normal startup.

RAG-managed tables must remain managed by the existing RAG service. Do not
recreate, modify, or take ownership of RAG tables unless explicitly required
by the existing integration contract.

---

## 7. Verification before ZIP creation

Before creating the final ZIP, actually execute the checks that are possible:

1. Verify frontend dependencies.
2. Run frontend linting.
3. Run frontend tests.
4. Run frontend production build.
5. Run backend compilation.
6. Run backend tests.
7. Run backend packaging.
8. Validate database migrations.
9. Check Dockerfile configuration where possible.
10. Verify environment variables are documented.
11. Verify frontend API configuration.
12. Verify backend health endpoint.
13. Verify authentication.
14. Verify role-based authorization.
15. Verify tenant isolation.
16. Verify lead creation and management.
17. Verify property management.
18. Verify property recommendations.
19. Verify site-visit booking.
20. Verify human-agent handover.
21. Verify RAG integration configuration.
22. Verify Voice Agent integration configuration.
23. Fix all errors that can be fixed.
24. Re-run failed checks after fixes.

Never claim a test, build, migration, or integration check passed unless it was
actually executed.

If RAG or Voice Agent testing is blocked by unavailable credentials, unavailable
services, network restrictions, or missing API contracts:

- Complete all other implementation work.
- Keep the integration code configurable.
- Use development-only mocks only when useful.
- Clearly label mocked or unverified behavior.
- Document the exact blocker.
- Document the required environment variables.
- Document the exact steps needed to verify the real integration later.

---

## 8. Documentation requirements

Create:

- Root README.md
- frontend/README.md
- backend/README.md
- database/README.md
- docs/architecture.md
- docs/api.md
- docs/setup.md
- docs/integration.md
- docs/troubleshooting.md

The root README must include:

1. Application overview
2. Project structure
3. Prerequisites
4. Frontend setup
5. Backend setup
6. PostgreSQL setup
7. Environment configuration
8. Database migration commands
9. Seed-data commands
10. Frontend run commands
11. Backend run commands
12. Frontend Docker commands
13. Backend Docker commands
14. Test commands
15. Build commands
16. API documentation
17. RAG configuration
18. Voice Agent configuration
19. Development login details, only if safely generated
20. Troubleshooting
21. Known limitations
22. Manual verification checklist

Documentation must not refer to:

- ASTRA
- This prompt
- Internal workspace paths
- Unavailable Git repositories
- Unavailable Git access

Write the documentation for a developer who receives only the ZIP file.

---

## 9. Final ZIP creation and delivery

After completing implementation and verification:

1. Create a clean source-code ZIP archive.
2. Verify that the ZIP opens successfully.
3. Verify that frontend and backend folders are present.
4. Verify that all required source files are included.
5. Verify that Dockerfiles are included in the appropriate repositories.
6. Verify that environment examples are included.
7. Verify that database migrations are included.
8. Verify that no secrets are included.
9. Verify that no generated dependency folders are included.
10. Verify that no Git metadata is included.
11. Verify that the project can be extracted into another folder.
12. Provide the downloadable ZIP artifact.

The final response must contain:

- Downloadable ZIP file
- ZIP contents summary
- Frontend folder name
- Backend folder name
- Frontend setup command
- Backend setup command
- Frontend Docker command
- Backend Docker command
- Required environment variables
- Tests executed
- Builds executed
- Known limitations
- Remaining manual configuration

Do not mark the task complete until the source-code ZIP has been created.

Completion means:

The ZIP contains the complete React frontend, Spring Boot backend, PostgreSQL
configuration, migrations, Docker configuration, integration adapters, tests,
and documentation required for another developer to continue the project without
Git access or ASTRA access.

Do not provide only a plan, screenshots, explanations, partial files, or code
snippets. Deliver the actual complete source-code ZIP.

---

# CONSOLIDATED EXECUTION AND DELIVERY OVERRIDES

The following rules are mandatory and override any conflicting wording above.

## A. Work directly in the available workspace

- Inspect the workspace before changing anything.
- Preserve useful existing code and configuration.
- Create the actual files; do not only describe them.
- Do not stop after planning.
- Do not ask follow-up questions for normal implementation decisions.
- Make secure, practical, MVP-appropriate decisions autonomously.
- Ask only before destructive actions, irreversible database operations,
  production actions, secret changes, or actions outside the workspace.

## B. External research

When web access is available, use it selectively and only when it materially
improves implementation.

Prefer:
- Official React, Tailwind, Spring Boot, Spring Security, PostgreSQL, Docker,
  OpenAPI, Flyway/Liquibase, and accessibility documentation
- Official documentation for the existing RAG and Voice Agent services
- Reliable primary technical sources
- Reputable modern SaaS UI references

Research rules:
1. Verify version-sensitive or security-sensitive information.
2. Apply research directly to the implementation.
3. Do not repeatedly research the same decision.
4. Do not research unrelated technologies or out-of-scope features.
5. Do not copy proprietary code, branding, or designs.
6. If web access is unavailable, continue using reliable existing knowledge.
7. Never claim that a source was checked unless it was actually checked.
8. Document only important technical decisions.

## C. Token and execution optimization

- Read only relevant files and avoid rereading unchanged files.
- Use targeted searches.
- Reuse existing dependencies and components.
- Avoid duplicate services, DTOs, hooks, utilities, APIs, and abstractions.
- Avoid unnecessary microservices and overengineering.
- Batch safe related changes.
- Work in logical feature groups.
- Run focused checks after major feature groups.
- Fix errors directly and rerun failed checks.
- Keep logs, API responses, documentation, and final reports concise.
- Use mocks only when real external contracts or services are unavailable.
- Keep all RAG and Voice Agent integration behind replaceable adapters.
- Do not rebuild RAG, Voice Agent, embedding, prompt-management, or agent
  configuration functionality.

## D. Source-code ZIP delivery

I will not provide GitHub, GitLab, Git, branch, commit, or push access.

Deliver the finished application as a clean downloadable source-code ZIP,
similar to a source ZIP downloaded from GitHub.

The ZIP must contain:

real-estate-ai-mvp/
├── frontend/
├── backend/
├── database/
├── docs/
└── README.md

The frontend and backend must remain independently understandable projects.

### Frontend ZIP contents

Include:
- Complete React and Tailwind source
- package.json
- Lock file
- Build configuration
- Tests
- Dockerfile
- .dockerignore
- .env.example
- README.md
- Configurable backend API URL

### Backend ZIP contents

Include:
- Complete Spring Boot source
- pom.xml
- REST APIs
- DTOs and mappers
- Validation
- Security configuration
- Exception handling
- Database migration configuration
- Tests
- Dockerfile
- .dockerignore
- .env.example
- README.md
- Configurable RAG and Voice Agent adapters

### ZIP exclusions

Do not include:
- node_modules
- target
- build
- dist
- coverage
- logs
- caches
- IDE metadata
- local database files
- real .env files
- secrets, passwords, API keys, JWT secrets, private keys
- .git directories or Git metadata
- temporary or ASTRA-specific files
- absolute paths or machine-specific configuration

Use relative paths only. The extracted workspace must be movable to another
suitable folder or computer.

### Docker responsibility

Include Dockerfiles and relevant Docker configuration in each repository.
I will manage Docker networking, PostgreSQL startup, environment variables,
external service credentials, and service setup myself.

Do not require a root-level Compose workflow or create a universal installer.
A root-level Compose file may be included only if optional and clearly
documented.

## E. Environment configuration

Create safe example files only:
- frontend/.env.example
- backend/.env.example
- root .env.example only if genuinely needed

Document:
- Frontend API URL
- PostgreSQL URL, username, and password
- JWT secret
- RAG URL and authentication
- Voice Agent URL and authentication
- File storage
- Notifications
- CORS and allowed origins

Never include real credentials. Fail clearly when required configuration is
missing or invalid.

## F. Verification before completion

Actually execute every applicable check:

1. Frontend dependency verification
2. Frontend lint
3. Frontend tests
4. Frontend production build
5. Backend compilation
6. Backend tests
7. Backend packaging
8. Database migration validation
9. Dockerfile/configuration validation where possible
10. Backend health check
11. Authentication and authorization checks
12. Workspace-isolation checks
13. Lead, inventory, recommendation, site-visit, and handover checks
14. RAG and Voice Agent adapter/configuration checks
15. Fix errors and rerun failed checks

Never claim a check passed unless it was executed.

If external services cannot be tested, document:
- Exact blocker
- Affected feature
- Required variables or credentials
- Mocked versus verified behavior
- Exact later verification steps

## G. Documentation

Create:
- README.md
- frontend/README.md
- backend/README.md
- database/README.md
- docs/architecture.md
- docs/api.md
- docs/setup.md
- docs/integration.md
- docs/troubleshooting.md

Documentation must be usable by a developer who receives only the ZIP and
must not refer to ASTRA, this prompt, internal paths, or Git access.

## H. Final delivery report

After creating the ZIP:
1. Verify that it opens.
2. Verify expected folders and files.
3. Verify migrations and Dockerfiles are included.
4. Verify no secrets, generated dependencies, or Git metadata are included.
5. Provide the downloadable ZIP artifact.

The final response must contain:
- ZIP artifact
- Contents summary
- Frontend and backend locations
- Setup commands
- Docker commands for each repository
- Required environment variables
- Tests/builds actually executed
- Known limitations
- Remaining manual configuration

Do not mark the task complete until the actual source-code ZIP exists.
