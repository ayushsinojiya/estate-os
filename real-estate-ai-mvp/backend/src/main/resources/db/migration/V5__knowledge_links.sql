-- Files uploaded on the Files page are also workspace-wide sources in the knowledge service.
-- The CRM keeps the link and the last status it observed; the knowledge service owns the content.
ALTER TABLE managed_files
  ADD COLUMN knowledge_source_id uuid,
  ADD COLUMN knowledge_status varchar(20),
  ADD COLUMN knowledge_error varchar(500);
CREATE INDEX idx_managed_files_knowledge ON managed_files(workspace_id, knowledge_status)
  WHERE knowledge_status IS NOT NULL;
