# File Upload & Storage System — Implementation Plan

## Objective

Implement a complete **file upload, validation, storage, history, and management feature** from scratch inside the existing Astra Estate OS application.

This is a **full-stack feature** covering:

- Frontend
- Backend
- Database
- Authentication/authorization integration
- Workspace isolation
- File-system storage
- Validation
- SHA-256 duplicate detection
- Upload history
- Delete flow
- Error/status handling
- Testing and verification

This task **does not include RAG parsing, chunking, embeddings, vector storage, or document indexing**. The responsibility ends after a valid file is safely stored and its metadata/status is persisted.

---

## 1. Mandatory Project Discovery

Before changing any code, read:

`astra_estate_os_mvp_prompt.md`

Treat that file and the existing codebase as the source of truth for:

- frontend and backend technologies
- project/module structure
- database and ORM
- migration strategy
- API conventions
- JWT authentication
- `workspace_id` handling
- authorization
- DTO/schema conventions
- error handling
- API response format
- logging
- naming conventions
- frontend architecture
- routing
- API/client layer
- state management
- forms
- notifications/toasts
- tables
- pagination
- search/filter controls
- loading/empty/error states
- visual design system
- testing conventions

Then inspect the actual relevant code before designing the implementation.

Do not assume architecture that can be discovered from the repository.

If the prompt and implementation differ, prefer the established application implementation unless doing so would break an explicit requirement in this task.

Do not replace existing project-wide patterns with a new architecture merely for this feature.

---

## 2. Planning Before Coding

After discovery, internally create an implementation plan covering:

1. Existing architecture and reusable patterns
2. Database changes
3. Backend components
4. Storage design
5. Validation flow
6. Duplicate-detection flow
7. API design
8. Frontend integration
9. Security/workspace isolation
10. Delete behavior
11. Error/status handling
12. Tests
13. Build/runtime verification

Proceed automatically once the repository provides enough information.

Do **not** stop for approval between planning and implementation.

Only ask for clarification if a genuinely blocking requirement cannot be determined from:

1. this file,
2. `astra_estate_os_mvp_prompt.md`,
3. existing application code/configuration.

Do not ask questions for implementation details that can reasonably follow existing app-wide conventions.

---

# 3. Functional Flow

Implement the following end-to-end flow:

```text
User
  ↓
Select one or multiple files
  ↓
Frontend validation
  ↓
Authenticated multipart upload
  ↓
Backend authentication
  ↓
Resolve workspace_id using existing application security model
  ↓
Validate each file independently
  ↓
Calculate SHA-256
  ↓
Check duplicate within workspace
  ↓
Persist/update file-history state
  ↓
Store valid file
  ↓
Persist final metadata/status
  ↓
Return per-file result
  ↓
Frontend refreshes/displays file history
```

Multiple selected files must be treated as **independent file entities**.

A failure for one file must not incorrectly make successful files appear failed.

---

# 4. Storage Configuration

The root upload location must be configurable through environment configuration.

Use a clear environment variable consistent with the project's naming conventions, conceptually:

```env
FILE_STORAGE_PATH=/path/to/storage
```

The exact configuration/property integration should follow the existing backend's configuration approach.

Do not hardcode an absolute machine-specific path.

Create internal directories underneath the configured root as needed.

The storage structure must:

- support multiple workspaces
- avoid filename collisions
- prevent one workspace from accessing another workspace's files
- be deterministic/manageable
- keep user-supplied filenames from controlling arbitrary filesystem paths
- work on the operating systems/environments already supported by the project

A reasonable conceptual structure is:

```text
<FILE_STORAGE_PATH>/
  <workspace-scope>/
    <internal-file-identifier>/
      <stored-file>
```

This is guidance, not a requirement to ignore superior existing application conventions.

Never trust a client-provided path.

---

# 5. Supported File Types

Support common file formats relevant to a real-estate CRM and future RAG ingestion.

At minimum support appropriate variants of:

### Documents

- PDF
- DOC
- DOCX
- TXT
- MD

### Spreadsheets / structured data

- XLS
- XLSX
- CSV

### Presentations

- PPT
- PPTX

### Images

- JPG
- JPEG
- PNG
- WEBP

### Archives

- ZIP

ZIP is accepted as a **single uploaded file entity**.

Do not extract or process ZIP contents as part of this feature.

Centralize the supported-type configuration/validation instead of scattering extension lists throughout the code.

---

# 6. File Size

Maximum size:

```text
50 MB per file
```

Enforce the limit on the backend regardless of frontend validation.

Also configure framework/server multipart limits where required so that the application can actually receive valid 50 MB files.

The frontend should reject obviously oversized files before upload and display a clear message.

Do not introduce an arbitrary combined multi-file upload limit unless the existing application/infrastructure requires one.

---

# 7. Validation

Keep validation intentionally simple but safe.

Validate at minimum:

- file exists in request
- filename exists
- file is not empty
- maximum 50 MB/file
- supported extension/type
- sanitized filename
- safe storage path
- path traversal protection
- SHA-256 duplicate rule
- authenticated workspace context

Use MIME/type information when reasonably available, but do not create an unnecessarily complex content-inspection subsystem.

Never trust:

- raw filename
- extension alone where an existing safe validation utility exists
- client-supplied filesystem paths
- client-supplied `workspace_id` when workspace context should come from authenticated authorization state

Validation failures must produce user-friendly reasons that can be displayed by the frontend.

---

# 8. SHA-256 Duplicate Detection

Calculate a SHA-256 checksum for every valid upload.

Duplicate detection must be scoped by:

```text
workspace_id + SHA-256
```

### Rule

If the same workspace already has the same file and its relevant existing record represents a successfully stored/active file:

```text
Reject the new upload.
```

Return a clear user-facing message similar in meaning to:

```text
This file has already been uploaded.
```

Do not create another physical copy.

### Failed uploads

If the previous attempt exists only as a failed upload/storage attempt:

```text
Allow re-upload.
```

The data model/query/index strategy must support this requirement correctly.

### Deleted files

Because deletion removes the physical file but preserves its audit/history record, a previously deleted file must be uploadable again.

Historical deleted records must not permanently block a new upload.

Avoid race conditions where two concurrent requests could bypass duplicate detection. Use database constraints/transactions or the most appropriate mechanism supported by the existing stack.

---

# 9. File History Data Model

Design the schema according to the existing database conventions and real-estate CRM audit requirements.

Do not blindly use this exact schema, but ensure the final model captures the equivalent useful information.

Expected concepts include:

```text
id
workspace_id

original_file_name
stored_file_name
storage_path / storage_key
file_extension
mime_type
file_size_bytes
sha256_checksum

status
failure_reason

created/uploaded timestamp
updated timestamp
deleted timestamp where applicable

created_by / uploaded_by
```

Use the application's existing ID, audit, user, timestamp, enum, FK, and workspace patterns.

Do not expose sensitive physical server paths unnecessarily in normal frontend responses.

Create the appropriate database migration using the project's existing migration strategy.

Add indexes/constraints needed for:

- workspace history queries
- SHA-256 duplicate lookup
- status filtering
- common sorting/search patterns where justified

Keep the schema focused. Do not add speculative RAG fields that are not required yet.

---

# 10. Status Lifecycle

Create a small, meaningful lifecycle suitable for the current scope.

It must represent at least the concepts of:

```text
upload/storage in progress
successfully stored
failed
deleted
```

Choose exact enum/status names consistent with existing project conventions.

Do not add RAG statuses such as:

```text
CHUNKING
EMBEDDING
INDEXING
VECTOR_STORED
```

because RAG processing is outside this task.

Failure records must retain a meaningful reason suitable for displaying in the frontend.

Ensure transitions are internally consistent.

---

# 11. Failure Handling

If validation or storage fails after a history entity should reasonably exist:

- record failure status
- record a useful failure reason
- do not report success
- clean up incomplete physical files where applicable
- preserve useful history/audit information

Do not expose:

- stack traces
- internal filesystem details
- secrets
- sensitive implementation details

to the frontend.

Unexpected errors should use the application's standard error handling/logging.

---

# 12. Delete Behavior

Users must be able to delete a stored file through the application.

Deletion means:

```text
Remove physical file from storage
+
Keep database history
+
Mark record as deleted
```

Do not hard-delete the history record.

Record the appropriate deletion timestamp/audit information according to project conventions.

After successful deletion:

- file is no longer considered active
- it must not appear as an active stored file
- its history remains available as appropriate
- the same SHA-256 may be uploaded again later

Authorization and `workspace_id` isolation must be enforced server-side.

Handle cases where the DB record exists but the physical file is already missing in a safe, predictable way.

---

# 13. Backend APIs

Design APIs according to the application's existing API conventions.

The feature requires, conceptually:

### Upload

```text
POST <appropriate-file-endpoint>
Content-Type: multipart/form-data
```

Must support one or multiple files.

Return useful **per-file** outcomes.

### History

```text
GET <appropriate-file-endpoint>
```

Support application-standard:

- pagination
- sorting
- filename search
- status filtering

Default sorting should follow the application's table/list conventions, normally newest uploads first if no stronger convention exists.

### Delete

```text
DELETE <appropriate-file-endpoint>/{id}
```

Deletes physical storage while preserving history.

### Detail endpoint

Add a detail endpoint only if it is actually useful for the frontend flow or consistent with existing application patterns.

### Do NOT implement

A file download/view API is **not required** for this task.

Do not expose the storage root or physical file paths as a substitute.

Avoid unnecessary APIs such as manual retry endpoints when re-uploading a failed file already satisfies the required retry behavior.

---

# 14. Authentication & Workspace Isolation

The application uses:

```text
JWT
+
workspace_id
```

Integrate with the existing authentication/authorization implementation.

Do not invent a second authentication mechanism.

Every backend operation must enforce workspace isolation.

A user from Workspace A must never be able to:

- see Workspace B's history
- delete Workspace B's files
- affect Workspace B's duplicate checks
- access Workspace B's storage records

Do not trust arbitrary frontend workspace IDs if the established security context provides the authoritative workspace.

Follow existing role/permission conventions if file-management access needs to map to current CRM permissions.

---

# 15. Frontend Feature

Implement the complete frontend experience using existing app-wide UI and architecture standards.

Do not introduce a separate design system.

The feature should provide a clear file-management/upload experience including:

- file selector
- multiple-file selection
- selected-file list
- basic client-side validation
- upload action
- upload/loading state
- per-file success/failure feedback
- duplicate message
- history table
- delete action
- deletion confirmation using existing UX conventions
- pagination
- filename search
- status filter
- app-standard sorting
- loading state
- empty state
- error state

Where useful, show metadata such as:

- filename
- type
- size
- status
- uploaded by
- upload date/time
- failure reason
- deletion state/date

Choose the final columns based on existing table patterns and available audit data.

### Table requirement

The history table **must follow existing application-wide table standards**.

Before implementing it, inspect other production tables in the frontend and reuse their established:

- table component
- pagination
- filters
- search
- typography
- spacing
- actions
- confirmation behavior
- badges/status representation
- responsive behavior
- empty/loading states

Do not create a visually inconsistent custom table.

---

# 16. Multi-File UX

When multiple files are selected, each is an independent entity.

Example:

```text
brochure.pdf       → STORED
inventory.xlsx     → STORED
brochure-copy.pdf  → DUPLICATE / rejected
large-video.mp4    → validation failure
```

The UI must clearly communicate individual outcomes.

One failed file must not hide successful results.

After an upload attempt, refresh/invalidate history using the existing frontend data-fetching conventions.

---

# 17. Security Requirements

At minimum protect against:

- path traversal
- malicious filenames
- workspace data leakage
- unauthorized deletion
- arbitrary storage path injection
- duplicate bypass
- oversized uploads
- unsupported file uploads
- unsafe filesystem naming
- accidental overwrite of another stored file

Use safe generated/internal identifiers for physical storage where appropriate.

Never concatenate an untrusted filename directly into an unrestricted filesystem path.

Do not add unnecessary public/static serving of the upload directory.

---

# 18. Transaction & Filesystem Consistency

Database and filesystem operations cannot necessarily share one atomic transaction.

Design the flow carefully.

Avoid situations where:

```text
DB says STORED but file does not exist
```

or orphaned partial files remain after failed operations.

Use a sensible sequence such as temporary/write-safe storage + DB state transitions/cleanup, adapted to the existing stack.

If an operation partially fails:

- attempt cleanup
- preserve accurate status
- log the technical error
- return a safe user-facing message

Keep this implementation simple, but correctness matters.

---

# 19. Code Organization

Follow existing architecture.

Create/reuse appropriate components such as the project's equivalent of:

- controller/router
- service
- repository/data access
- entity/model
- DTO/schema
- mapper
- validator
- storage service
- checksum utility
- configuration
- migration
- frontend API/client
- frontend page/components

Do not create abstractions merely to increase layering.

However, filesystem operations, SHA-256 calculation, validation, and persistence logic should not all be dumped into a controller.

Keep the design ready for future RAG integration without implementing RAG now.

---

# 20. Configuration & Documentation

Update the appropriate example/config documentation with the new storage variable.

Document:

- environment variable
- expected storage-root behavior
- 50 MB limit
- supported file types
- relevant local setup requirements

Never commit machine-specific absolute paths or secrets.

Preserve existing environment files and conventions.

---

# 21. Tests

Add tests consistent with the project's existing test setup.

Cover the important behavior at minimum.

### Backend

Test scenarios such as:

1. valid single-file upload
2. valid multiple-file upload
3. 50 MB boundary behavior where practical
4. oversized file rejection
5. unsupported format
6. empty file
7. SHA-256 generation
8. duplicate in same workspace rejected
9. failed previous upload can be uploaded again
10. deleted previous upload can be uploaded again
11. same checksum in another workspace does not conflict
12. history pagination
13. history search
14. history status filter
15. delete removes physical file
16. delete preserves history
17. unauthorized/cross-workspace access rejected
18. malicious/path-traversal filename handled safely
19. storage failure records correct status/reason where applicable

### Frontend

Use the project's existing frontend testing approach where available.

Cover high-value behavior such as:

- multiple selection
- basic validation
- API integration
- per-file result rendering
- duplicate/error feedback
- history state
- delete flow

Do not introduce a large new testing framework solely for this feature unless necessary.

---

# 22. Verification

Do not consider the feature complete just because code was written.

Run all relevant verification available in the repository.

At minimum, as applicable:

```text
backend compile/build
backend tests
frontend type checking
frontend lint
frontend tests
frontend production build
database migration validation
```

Fix errors caused by this implementation.

Also inspect the final changes for:

- broken imports
- dead code
- inconsistent naming
- accidental unrelated modifications
- hardcoded paths
- missing workspace filters
- incorrect status transitions
- unsafe file handling
- frontend/backend contract mismatches

If the environment prevents a verification step, report the exact blocked step and reason rather than claiming it passed.

---

# 23. Scope Boundaries

### Implement

```text
FE file selection
multi-file upload
FE validation
BE multipart handling
BE validation
50 MB/file limit
common real-estate file formats
ZIP as a file
SHA-256 hashing
workspace-scoped duplicate detection
configurable filesystem storage
file metadata/history persistence
status/failure tracking
history UI
pagination/search/filter/sort
physical deletion
retained deletion history
JWT/workspace security
tests
build verification
```

### Do NOT implement

```text
document parsing
ZIP extraction
OCR
chunking
embeddings
vector database insertion
RAG indexing
LLM calls
document Q&A
file preview
file download API
cloud/object storage migration
background job infrastructure unless the existing architecture requires it
```

Do not expand scope into these areas.

---

# 24. Definition of Done

The feature is complete only when all of the following are true:

- user can select one or multiple supported files from the frontend
- each file is handled independently
- maximum file size is 50 MB
- backend performs authoritative validation
- files are stored under an environment-configurable root
- storage is workspace-safe
- SHA-256 is generated
- active duplicate within the same workspace is rejected
- duplicate rejection clearly tells the user it was already uploaded
- a previously failed upload can be uploaded again
- a previously deleted file can be uploaded again
- file metadata/history is persisted
- statuses accurately reflect outcomes
- failure reasons are available to the frontend
- history supports app-standard pagination/search/filter/sort
- frontend table follows application-wide table standards
- delete removes the physical file
- delete retains the database history
- JWT and workspace isolation are enforced
- no download/view API is introduced
- no RAG processing is introduced
- relevant tests pass
- frontend/backend builds pass
- migrations are valid
- no unrelated existing functionality is knowingly broken

---

# 25. Final Report

After implementation and verification, provide a concise implementation report containing:

### Implemented

Summarize what was added.

### Architecture

Explain the final upload/storage flow and important design choices.

### Files Changed

List important created/modified files grouped by:

- frontend
- backend
- database/migrations
- configuration
- tests

### Database

Describe the created/changed schema, indexes, statuses, and duplicate strategy.

### APIs

List the final endpoints and their purpose.

### Storage

State the final environment variable and internal storage structure.

### Validation

List the implemented validation rules.

### Security

Explain workspace isolation and path/filename protection.

### Verification

Report the exact build/test/lint/typecheck/migration commands executed and their results.

### Remaining Notes

Only include genuine limitations, blocked verification, or necessary follow-up work.

Do not claim a test/build passed unless it was actually executed successfully.
