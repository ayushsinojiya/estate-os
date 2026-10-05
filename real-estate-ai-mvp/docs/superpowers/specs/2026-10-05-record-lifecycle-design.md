# CRM record lifecycle actions

Lead and conversation removal is recoverable: rows remain for audit and foreign-key history but disappear from ordinary reads, lists, related records, and dashboard totals. Only workspace managers/admins can remove them. An active call, visit, or unfinished handover blocks lead removal; scheduled callbacks, calls, and follow-up reminders are cancelled when a lead is removed. Creating a new lead with the same phone starts a fresh record.

Completed/failed conversations can be removed. Pending or in-progress conversations cannot be cancelled because the configured voice provider has no reliable stop operation; the UI must not imply otherwise.

Site visits and callbacks use their existing cancellation lifecycles. Offer cancellation in the main site-visit views, prevent terminal visits being cancelled again, and ask for confirmation before cancellation. Existing file/source and blackout deletion remains unchanged. Do not add deletion to completed handovers, projects, or inventory: those records have separate status/history workflows.

Every new action needs a clear confirmation, busy/error handling, query refresh, an accessible name, and backend and frontend regression coverage. No live customer records are deleted during verification.
