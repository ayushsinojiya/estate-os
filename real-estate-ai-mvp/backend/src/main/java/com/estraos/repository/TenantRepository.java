package com.estraos.repository;

import com.estraos.dto.PageResponse;
import com.estraos.exception.ApiException;
import com.estraos.mapper.DtoMapper;
import java.sql.*;
import java.time.*;
import java.util.*;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/** SQL identifiers are fixed in code; all caller values use bound parameters. */
@Repository
public class TenantRepository {
  private static final Set<String> TABLES =
      Set.of(
          "projects",
          "buildings",
          "floors",
          "unit_types",
          "units",
          "leads",
          "property_documents",
          "voice_sessions",
          "appointments",
          "handover_records",
          "lead_recommendations",
          "notifications",
          "audit_logs",
          "project_locations",
          "project_amenities",
          "unit_status_history",
          "unit_prices",
          "lead_contacts",
          "lead_status_history",
          "lead_assignments",
          "lead_preferences",
          "lead_tags",
          "lead_notes",
          "lead_activities",
          "property_document_versions",
          "property_content",
          "property_content_versions",
          "voice_session_events",
          "voice_transcripts",
          "voice_summaries",
          "voice_session_requirements",
          "appointment_participants",
          "appointment_status_history",
          "notification_deliveries",
          "amenities",
          "lead_sources",
          "files",
          "api_request_logs",
          "outbox_events",
          "idempotency_keys",
          "visit_slot_templates",
          "visit_slot_blackouts",
          "project_agents",
          "callbacks",
          "dnc_numbers",
          "scheduled_calls");
  private final NamedParameterJdbcTemplate db;
  private final DtoMapper json;

  public TenantRepository(NamedParameterJdbcTemplate db, DtoMapper json) {
    this.db = db;
    this.json = json;
  }

  private String table(String table) {
    if (!TABLES.contains(table)) throw new IllegalArgumentException("Unsupported resource");
    return table;
  }

  public NamedParameterJdbcTemplate sql() {
    return db;
  }

  private String camel(String s) {
    StringBuilder out = new StringBuilder();
    boolean upper = false;
    for (char c : s.toCharArray()) {
      if (c == '_') {
        upper = true;
      } else {
        out.append(upper ? Character.toUpperCase(c) : c);
        upper = false;
      }
    }
    return out.toString();
  }

  public Map<String, Object> row(ResultSet rs, int number) throws SQLException {
    Map<String, Object> out = new LinkedHashMap<>();
    String data = rs.getString("data");
    if (data != null) out.putAll(json.read(data));
    var meta = rs.getMetaData();
    for (int i = 1; i <= meta.getColumnCount(); i++) {
      String key = meta.getColumnLabel(i);
      if (key.equals("data")) continue;
      Object v = rs.getObject(i);
      if (v instanceof Timestamp t) v = t.toInstant().toString();
      if (v instanceof Long) v = v.toString();
      out.put(camel(key), v);
    }
    return out;
  }

  public Map<String, Object> get(String table, Long ws, Long id) {
    var rows =
        db.query(
            "SELECT * FROM " + table(table) + " WHERE workspace_id=:ws AND id=:id",
            Map.of("ws", ws, "id", id),
            this::row);
    if (rows.isEmpty()) throw ApiException.missing();
    return rows.getFirst();
  }

  public List<Map<String, Object>> related(String table, Long ws, String column, Long id) {
    if (!Set.of(
            "project_id",
            "lead_id",
            "unit_id",
            "document_id",
            "voice_session_id",
            "appointment_id",
            "notification_id")
        .contains(column)) throw new IllegalArgumentException("Invalid relation");
    return db.query(
        "SELECT * FROM "
            + table(table)
            + " WHERE workspace_id=:ws AND "
            + column
            + "=:id ORDER BY created_at DESC",
        Map.of("ws", ws, "id", id),
        this::row);
  }

  public PageResponse<Map<String, Object>> list(
      String table, Long ws, Map<String, String> filters) {
    int page = integer(filters.get("page"), 0), size = integer(filters.get("size"), 20);
    if (page < 0 || page > 100000 || size < 1 || size > 100)
      throw ApiException.bad("Page must be nonnegative and size between 1 and 100");
    StringBuilder where = new StringBuilder(" WHERE workspace_id=:ws");
    Map<String, Object> p = new HashMap<>();
    p.put("ws", ws);
    String search = filters.get("search");
    if (search != null && !search.isBlank()) {
      where.append(" AND (data::text ILIKE :search");
      if (Set.of("projects", "leads", "buildings", "unit_types").contains(table))
        where.append(" OR name ILIKE :search");
      if (table.equals("leads")) where.append(" OR phone ILIKE :search OR email ILIKE :search");
      if (table.equals("units")) where.append(" OR unit_number ILIKE :search");
      if (table.equals("property_documents")) where.append(" OR title ILIKE :search");
      where.append(")");
      p.put("search", "%" + search.replace("%", "\\%").replace("_", "\\_") + "%");
    }
    if (filters.containsKey("status") && !filters.get("status").isBlank()) {
      if (!Set.of(
              "projects",
              "units",
              "leads",
              "property_documents",
              "voice_sessions",
              "appointments",
              "handover_records",
              "notifications",
              "callbacks",
              "scheduled_calls")
          .contains(table))
        throw ApiException.bad("Status filtering is not supported on this resource");
      where.append(" AND status=:status");
      p.put("status", filters.get("status"));
    }
    for (String key : List.of("projectId", "leadId", "agentId", "buildingId")) {
      if (filters.containsKey(key) && !filters.get(key).isBlank()) {
        boolean supported =
            switch (key) {
              case "projectId" ->
                  Set.of(
                          "units",
                          "buildings",
                          "floors",
                          "unit_types",
                          "property_documents",
                          "appointments",
                          "handover_records")
                      .contains(table);
              case "leadId" ->
                  Set.of("voice_sessions", "appointments", "handover_records", "callbacks",
                          "scheduled_calls")
                      .contains(table);
              case "agentId" -> Set.of("leads", "appointments", "handover_records").contains(table);
              default -> Set.of("units", "floors").contains(table);
            };
        if (!supported) throw ApiException.bad("Unsupported filter: " + key);
        String col =
            switch (key) {
              case "projectId" -> "project_id";
              case "leadId" -> "lead_id";
              case "agentId" -> table.equals("leads") ? "assigned_agent_id" : "agent_id";
              default -> "building_id";
            };
        where.append(" AND ").append(col).append("=:").append(key);
        long relatedId = Long.parseLong(filters.get(key));
        if (relatedId <= 0) throw ApiException.bad("Filter IDs must be positive");
        p.put(key, relatedId);
      }
    }
    if (table.equals("notifications") && filters.containsKey("recipientUserId")) {
      where.append(" AND (user_id=:recipient OR user_id IS NULL)");
      p.put("recipient", Long.valueOf(filters.get("recipientUserId")));
    }
    for (String key : List.of("source", "language", "location", "propertyType", "bhk")) {
      if (filters.containsKey(key) && !filters.get(key).isBlank()) {
        if (!Set.of("leads", "units", "projects").contains(table))
          throw ApiException.bad("Unsupported filter: " + key);
        String expression =
            table.equals("units") && key.equals("bhk")
                ? "bhk::text"
                : table.equals("units") && key.equals("propertyType")
                    ? "property_type"
                    : "data->>'" + key + "'";
        where.append(" AND ").append(expression).append(" ILIKE :").append(key);
        p.put(key, filters.get(key));
      }
    }
    String requested = filters.getOrDefault("sort", "createdAt,desc");
    String[] parts = requested.split(",");
    String sort =
        switch (parts[0]) {
          case "name" ->
              Set.of("projects", "leads", "buildings", "unit_types").contains(table)
                  ? "name"
                  : "created_at";
          case "price" -> table.equals("units") ? "price" : "created_at";
          case "scheduledAt" -> table.equals("appointments") ? "scheduled_at" : "created_at";
          case "updatedAt" -> "updated_at";
          default -> "created_at";
        };
    String direction = parts.length > 1 && parts[1].equalsIgnoreCase("asc") ? "ASC" : "DESC";
    long total =
        Objects.requireNonNull(
            db.queryForObject("SELECT count(*) FROM " + table(table) + where, p, Long.class));
    p.put("limit", size);
    p.put("offset", (long) page * size);
    var items =
        db.query(
            "SELECT * FROM "
                + table(table)
                + where
                + " ORDER BY "
                + sort
                + " "
                + direction
                + ",id LIMIT :limit OFFSET :offset",
            p,
            this::row);
    return new PageResponse<>(items, total, page, size);
  }

  private int integer(String value, int fallback) {
    return value == null ? fallback : Integer.parseInt(value);
  }

  public Map<String, Object> save(
      String table, Long ws, Long id, Map<String, Object> data, Map<String, Object> columns) {
    boolean create = id == null;
    Map<String, Object> p = new HashMap<>(columns);
    p.put("id", id);
    p.put("ws", ws);
    p.put("data", json.write(data));
    if (create) {
      String names = String.join(",", columns.keySet());
      String values =
          columns.keySet().stream().map(k -> ":" + k).reduce((a, b) -> a + "," + b).orElse("");
      id =
          db.queryForObject(
              "INSERT INTO "
                  + table(table)
                  + "(workspace_id,data"
                  + (names.isEmpty() ? "" : "," + names)
                  + ") VALUES (:ws,CAST(:data AS jsonb)"
                  + (values.isEmpty() ? "" : "," + values)
                  + ") RETURNING id",
              p,
              Long.class);
    } else {
      String assignments =
          columns.keySet().stream().map(k -> k + "=:" + k).reduce((a, b) -> a + "," + b).orElse("");
      int n =
          db.update(
              "UPDATE "
                  + table(table)
                  + " SET data=CAST(:data AS jsonb),updated_at=now()"
                  + (assignments.isEmpty() ? "" : "," + assignments)
                  + " WHERE id=:id AND workspace_id=:ws",
              p);
      if (n != 1) throw ApiException.missing();
    }
    return get(table, ws, id);
  }

  public Map<String, Object> event(
      String table, Long ws, String column, Long parent, Map<String, Object> data) {
    return save(table, ws, null, data, Map.of(column, parent));
  }

  public void workspaceLock(Long ws) {
    db.getJdbcTemplate().queryForObject("SELECT pg_advisory_xact_lock(?)", Object.class, ws);
  }
}
