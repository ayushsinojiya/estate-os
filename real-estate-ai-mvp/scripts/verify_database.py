"""Read schema metadata and test constraints in a rolled-back transaction.

Requires Docker CLI and a running disposable PostgreSQL container. Override
DB_CONTAINER, DATABASE_USERNAME and DATABASE_NAME for your test setup.
"""
import os
import subprocess
import sys

TABLES = """workspaces users workspace_members roles permissions role_permissions
projects project_locations amenities project_amenities buildings floors unit_types
units unit_status_history unit_prices leads lead_contacts lead_sources
lead_status_history lead_assignments lead_preferences lead_tags lead_notes
lead_activities property_documents property_document_versions property_content
property_content_versions voice_sessions voice_session_events voice_transcripts
voice_summaries voice_session_requirements appointments appointment_participants
appointment_status_history handover_records notifications notification_deliveries
files audit_logs api_request_logs outbox_events idempotency_keys""".split()


def sql(query):
    if os.environ.get("PSQL_BIN"):
        command = [os.environ["PSQL_BIN"], "-h", os.environ.get("PGHOST", "127.0.0.1"),
                   "-p", os.environ.get("PGPORT", "5432")]
    else:
        command = ["docker", "exec", "-i", os.environ.get("DB_CONTAINER", "estraos-verification-db"), "psql"]
    command += ["-U", os.environ.get("DATABASE_USERNAME", "estraos"),
                "-d", os.environ.get("DATABASE_NAME", "estraos"), "-v", "ON_ERROR_STOP=1", "-Atq"]
    result = subprocess.run(command, input=query, text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())
    return result.stdout.strip()


def main():
    present = set(sql("SELECT table_name FROM information_schema.tables WHERE table_schema='public';").splitlines())
    missing = set(TABLES) - present
    assert not missing, "Missing tables: " + ", ".join(sorted(missing))
    print(f"PASS all {len(TABLES)} required business/support tables exist")
    global_tables = {"workspaces", "users", "roles", "permissions", "role_permissions"}
    for table in TABLES:
        columns = set(sql(f"SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='{table}';").splitlines())
        assert {"id", "created_at", "updated_at"} <= columns, table + " lacks audit columns"
        if table not in global_tables:
            assert "workspace_id" in columns, table + " lacks tenant column"
    print("PASS identity/audit/tenant column presence")
    checked = ",".join("'" + name + "'" for name in TABLES)
    wrong_ids = sql("SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='id' AND table_name IN (" + checked + ") AND (data_type<>'bigint' OR is_identity<>'YES');")
    assert not wrong_ids, "Non BIGINT identity identifiers: " + wrong_ids
    print("PASS BIGINT GENERATED identity primary keys on every required table")
    sql("""
BEGIN;
DO $$
DECLARE wa bigint; wb bigint; pa bigint; pb bigint; bb bigint;
BEGIN
 INSERT INTO workspaces(name) VALUES ('Constraint verification A') RETURNING id INTO wa;
 INSERT INTO workspaces(name) VALUES ('Constraint verification B') RETURNING id INTO wb;
 INSERT INTO projects(workspace_id,name,status) VALUES(wa,'A','ACTIVE') RETURNING id INTO pa;
 INSERT INTO projects(workspace_id,name,status) VALUES(wb,'B','ACTIVE') RETURNING id INTO pb;
 INSERT INTO buildings(workspace_id,project_id,name) VALUES(wb,pb,'B') RETURNING id INTO bb;
 BEGIN
  INSERT INTO units(workspace_id,project_id,building_id,unit_number,status,price,area,bhk,property_type)
  VALUES(wa,pa,bb,'X','AVAILABLE',100,100,1,'APARTMENT');
  RAISE EXCEPTION 'Cross-workspace building was accepted';
 EXCEPTION WHEN foreign_key_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO units(workspace_id,project_id,unit_number,status,price,area,bhk,property_type)
  VALUES(wa,pb,'X','AVAILABLE',100,100,1,'APARTMENT');
  RAISE EXCEPTION 'Cross-workspace project was accepted';
 EXCEPTION WHEN foreign_key_violation THEN NULL;
 END;
 INSERT INTO units(workspace_id,project_id,unit_number,status,price,area,bhk,property_type)
 VALUES(wa,pa,'A101','AVAILABLE',100,100,1,'APARTMENT');
 BEGIN
  INSERT INTO units(workspace_id,project_id,unit_number,status,price,area,bhk,property_type)
  VALUES(wa,pa,'a101','AVAILABLE',100,100,1,'APARTMENT');
  RAISE EXCEPTION 'Case-insensitive duplicate unit was accepted';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO units(workspace_id,project_id,unit_number,status,price,area,bhk,property_type)
  VALUES(wa,pa,'NEG','AVAILABLE',-1,100,1,'APARTMENT');
  RAISE EXCEPTION 'Negative unit price was accepted';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
 INSERT INTO leads(workspace_id,name,phone,email,status)
 VALUES(wa,'A','+910000000001','buyer@example.test','NEW');
 BEGIN
  INSERT INTO leads(workspace_id,name,phone,email,status)
  VALUES(wa,'A','+910000000002','BUYER@example.test','NEW');
  RAISE EXCEPTION 'Case-insensitive duplicate lead email was accepted';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 INSERT INTO leads(workspace_id,name,phone,email,status)
 VALUES(wb,'B','+910000000001','buyer@example.test','NEW');
END $$;
ROLLBACK;
""")
    print("PASS cross-tenant foreign keys, duplicate unit/email, nonnegative price, per-tenant contacts")
    print("PASS constraint probes rolled back; existing business data preserved")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL " + str(error), file=sys.stderr)
        sys.exit(1)
