ALTER TABLE leads ADD COLUMN deleted_at timestamptz;
ALTER TABLE voice_sessions ADD COLUMN deleted_at timestamptz;

DROP INDEX uq_leads_phone;
CREATE UNIQUE INDEX uq_leads_phone ON leads(workspace_id, phone) WHERE deleted_at IS NULL;
DROP INDEX uq_leads_email;
CREATE UNIQUE INDEX uq_leads_email ON leads(workspace_id, lower(email))
  WHERE email IS NOT NULL AND email <> '' AND deleted_at IS NULL;

CREATE INDEX idx_leads_visible ON leads(workspace_id, id) WHERE deleted_at IS NULL;
CREATE INDEX idx_voice_sessions_visible ON voice_sessions(workspace_id, id) WHERE deleted_at IS NULL;
