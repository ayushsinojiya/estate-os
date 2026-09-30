-- EstraOS Pune synthetic inventory loader
--
-- Creates 25 fictional Pune developments and 1,000 fictional property records
-- (40 units per development). This is demo data only: it is not sourced from,
-- affiliated with, or offered by any real developer or property owner.
--
-- Run against a local PostgreSQL database after Flyway migrations and the demo seed:
--   psql -v ON_ERROR_STOP=1 -U postgres -d estra_os -f database/seed/pune_synthetic_properties.sql
--
-- Change target_workspace_name below only when the local demo workspace has a
-- different name. The script never creates a workspace and is safe to rerun.

BEGIN;

DO $$
DECLARE
  target_workspace_name constant text := 'Westhaven Realty · Demo';
  target_workspace_id bigint;
  workspace_matches integer;
  project_id bigint;
  project_index integer;
  unit_index integer;
  inserted_projects integer := 0;
  inserted_units integer := 0;
  existing_units integer;
  development_names constant text[] := ARRAY[
    'Sahyadri Grove', 'Mula Vista', 'Deccan Courtyard', 'Pashan Canopy', 'Kharadi Meadows',
    'Baner Cedar Park', 'Wakad Terraces', 'Aundh Willow Homes', 'Hadapsar Greenway', 'NIBM Orchard',
    'Bavdhan Ridge', 'Viman Nagar Square', 'Kondhwa Gardens', 'Hinjawadi Skyline', 'Balewadi Courtyard',
    'Moshi Fields', 'Ravet Junction', 'Kothrud Arches', 'Magarpatta Grove', 'Wagholi Rise',
    'Undri Vista', 'Koregaon Park Lane', 'Tathawade Heights', 'Sus Hillside', 'Dhanori Parkside'
  ];
  neighbourhoods constant text[] := ARRAY[
    'Pashan', 'Kharadi', 'Baner', 'Wakad', 'Aundh',
    'Hadapsar', 'NIBM Road', 'Bavdhan', 'Viman Nagar', 'Kondhwa',
    'Hinjawadi', 'Balewadi', 'Moshi', 'Ravet', 'Kothrud',
    'Magarpatta', 'Wagholi', 'Undri', 'Koregaon Park', 'Tathawade',
    'Sus', 'Dhanori', 'Mundhwa', 'Warje', 'Dhayari'
  ];
  property_kinds constant text[] := ARRAY[
    'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT',
    'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT',
    'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT',
    'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT', 'APARTMENT',
    'VILLA', 'VILLA', 'PLOT', 'PLOT', 'COMMERCIAL'
  ];
  property_kind text;
  unit_area numeric(12, 2);
  unit_price numeric(16, 2);
  bedrooms integer;
  unit_status text;
  possession_date date;
BEGIN
  PERFORM pg_advisory_xact_lock(982001000);

  SELECT count(*), min(id)
    INTO workspace_matches, target_workspace_id
    FROM workspaces
   WHERE name = target_workspace_name;

  IF workspace_matches = 0 THEN
    RAISE EXCEPTION 'Workspace "%" was not found. Update target_workspace_name before running this loader.', target_workspace_name;
  ELSIF workspace_matches > 1 THEN
    RAISE EXCEPTION 'Workspace "%" is ambiguous (% matches). Use a uniquely named local workspace.', target_workspace_name, workspace_matches;
  END IF;

  FOR project_index IN 1..25 LOOP
    property_kind := property_kinds[project_index];
    possession_date := make_date(2026 + (project_index % 3), ((project_index * 3) % 12) + 1, 1);

    SELECT id INTO project_id
      FROM projects
     WHERE projects.workspace_id = target_workspace_id
       AND data ->> 'seedKey' = format('pune-synthetic-project-%s', lpad(project_index::text, 2, '0'));

    IF project_id IS NULL THEN
      INSERT INTO projects (workspace_id, name, status, data)
      VALUES (
        target_workspace_id,
        development_names[project_index],
        'ACTIVE',
        jsonb_build_object(
          'seedKey', format('pune-synthetic-project-%s', lpad(project_index::text, 2, '0')),
          'isSynthetic', true,
          'city', 'Pune',
          'state', 'Maharashtra',
          'country', 'India',
          'location', neighbourhoods[project_index] || ', Pune',
          'developer', 'Fictional Pune Habitat Co.',
          'description', 'Fictional Pune demo development generated for local EstraOS testing.',
          'possessionDate', possession_date::text,
          'amenities', 'Clubhouse, fitness studio, landscaped garden, visitor parking'
        )
      )
      RETURNING id INTO project_id;
      inserted_projects := inserted_projects + 1;
    END IF;

    FOR unit_index IN 1..40 LOOP
      unit_status := CASE
        WHEN unit_index <= 34 THEN 'AVAILABLE'
        WHEN unit_index <= 37 THEN 'RESERVED'
        WHEN unit_index <= 39 THEN 'SOLD'
        ELSE 'BLOCKED'
      END;

      bedrooms := CASE
        WHEN property_kind = 'PLOT' OR property_kind = 'COMMERCIAL' THEN 0
        WHEN property_kind = 'VILLA' THEN 3 + (unit_index % 2)
        ELSE 1 + (unit_index % 4)
      END;

      unit_area := CASE property_kind
        WHEN 'VILLA' THEN 1800 + ((unit_index * 137) % 2200)
        WHEN 'PLOT' THEN 1000 + ((unit_index * 211) % 3500)
        WHEN 'COMMERCIAL' THEN 550 + ((unit_index * 173) % 3800)
        ELSE 520 + ((unit_index * 89 + project_index * 31) % 1850)
      END;

      unit_price := CASE property_kind
        WHEN 'VILLA' THEN 18000000 + unit_area * 7800 + project_index * 125000
        WHEN 'PLOT' THEN 5500000 + unit_area * 2600 + project_index * 85000
        WHEN 'COMMERCIAL' THEN 8500000 + unit_area * 5100 + project_index * 175000
        ELSE 4200000 + unit_area * 6100 + project_index * 95000
      END;

      INSERT INTO units (workspace_id, project_id, unit_number, status, price, area, bhk, property_type, data)
      SELECT
        target_workspace_id,
        project_id,
        format('PUNE-%s-%s', lpad(project_index::text, 2, '0'), lpad(unit_index::text, 3, '0')),
        unit_status,
        unit_price,
        unit_area,
        bedrooms,
        property_kind,
        jsonb_build_object(
          'seedKey', format('pune-synthetic-unit-%s-%s', lpad(project_index::text, 2, '0'), lpad(unit_index::text, 3, '0')),
          'isSynthetic', true,
          'listingTitle', format('Fictional %s in %s, Pune', initcap(lower(property_kind)), neighbourhoods[project_index]),
          'city', 'Pune',
          'state', 'Maharashtra',
          'country', 'India',
          'locality', neighbourhoods[project_index],
          'facing', (ARRAY['East', 'West', 'North', 'South'])[1 + ((project_index + unit_index) % 4)],
          'floor', CASE WHEN property_kind = 'APARTMENT' THEN 1 + ((unit_index - 1) % 20) ELSE NULL END,
          'furnishing', CASE WHEN property_kind IN ('VILLA', 'APARTMENT') THEN (ARRAY['Unfurnished', 'Semi-furnished', 'Furnished'])[1 + (unit_index % 3)] ELSE NULL END,
          'currency', 'INR',
          'source', 'EstraOS Pune synthetic data loader'
        )
      WHERE NOT EXISTS (
        SELECT 1
          FROM units u
         WHERE u.workspace_id = target_workspace_id
           AND u.data ->> 'seedKey' = format('pune-synthetic-unit-%s-%s', lpad(project_index::text, 2, '0'), lpad(unit_index::text, 3, '0'))
      );

      IF FOUND THEN
        inserted_units := inserted_units + 1;
      END IF;
    END LOOP;
  END LOOP;

  SELECT count(*) INTO existing_units
    FROM units
   WHERE units.workspace_id = target_workspace_id
     AND data ->> 'source' = 'EstraOS Pune synthetic data loader';

  IF existing_units <> 1000 THEN
    RAISE EXCEPTION 'Pune synthetic loader expected 1,000 units but found %.', existing_units;
  END IF;

  RAISE NOTICE 'Pune synthetic loader complete: % projects and % units inserted; 1,000 synthetic units are present.', inserted_projects, inserted_units;
END $$;

COMMIT;
