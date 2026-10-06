package com.estraos.service;

import com.estraos.integration.RagServiceClient;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Turns the files in File management into Projects & inventory.
 *
 * <p>The knowledge service reads each published file into projects and listings (see its
 * {@code extract} module); this applies them here. A named project in a file becomes that project
 * (or adds to the existing one of the same name); listings without a project are grouped into one
 * project per locality, "Aundh listings". Every imported unit and project remembers the files it came
 * from, so a swapped file updates them, and a deleted or unpublished file takes its units off the
 * market (UNAVAILABLE) and an emptied imported project out of the active list (INACTIVE). Nothing is
 * hard-deleted, and a unit someone marked SOLD, RESERVED or BLOCKED keeps that status.
 */
@Service
public class KnowledgeInventoryImport {
  private static final Logger log = LoggerFactory.getLogger(KnowledgeInventoryImport.class);
  private static final TypeReference<Map<String, Object>> MAP = new TypeReference<>() {};
  private static final DateTimeFormatter MONTH_YEAR = new DateTimeFormatterBuilder()
      .parseCaseInsensitive().appendPattern("[MMMM yyyy][MMM yyyy][MMM-yyyy][MM/yyyy]")
      .toFormatter(Locale.ENGLISH);

  private final NamedParameterJdbcTemplate db;
  private final RagServiceClient rag;
  private final TransactionTemplate tx;
  private final ObjectMapper json;

  public KnowledgeInventoryImport(NamedParameterJdbcTemplate db, RagServiceClient rag,
      TransactionTemplate tx, ObjectMapper json) {
    this.db = db; this.rag = rag; this.tx = tx; this.json = json;
  }

  // ------------------------------------------------------------------ sync

  /** Every workspace: bring Projects & inventory in step with the files in the knowledge base. */
  public void syncAll() {
    for (Long ws : db.queryForList("SELECT id FROM workspaces ORDER BY id", Map.of(), Long.class)) {
      try {
        syncWorkspace(ws, false);
      } catch (RuntimeException e) {
        log.warn("Inventory import for workspace {} skipped this round: {}", ws, e.getMessage());
      }
    }
  }

  /** {@code retry} also re-reads files whose extraction failed (the "Sync now" button). */
  public List<Map<String, Object>> syncWorkspace(Long ws, boolean retry) {
    Map<String, Map<String, Object>> known = new HashMap<>();
    for (var row : imports(ws)) known.put(row.get("sourceId").toString(), row);
    Set<String> seen = new HashSet<>();
    for (int page = 0; page < 50; page++) {
      var items = list(rag.listSources(ws, page, 100).get("items"));
      for (var item : items) {
        if (item.get("crmDocumentId") != null) continue; // a project document: already part of its project
        String id = String.valueOf(item.get("id"));
        seen.add(id);
        var row = known.get(id);
        boolean settled = row != null && "PUBLISHED".equals(item.get("status"))
            && Objects.equals(number(row.get("version")), number(item.get("version")))
            && Set.of("IMPORTED", "EMPTY").contains(row.get("status"));
        if ((settled && !retry) || (row != null && "FAILED".equals(row.get("status")) && !retry
            && Objects.equals(number(row.get("version")), number(item.get("version"))))) continue;
        syncSource(ws, id, retry);
      }
      if (items.size() < 100) break;
    }
    // Files that left the list (deleted) are checked too: their inventory comes off the market.
    for (var entry : known.entrySet())
      if (!seen.contains(entry.getKey()) && !"REMOVED".equals(entry.getValue().get("status")))
        syncSource(ws, entry.getKey(), false);
    return imports(ws);
  }

  private void syncSource(Long ws, String sourceId, boolean retry) {
    Map<String, Object> result = rag.getExtraction(ws, sourceId, retry);
    String status = String.valueOf(result.get("status"));
    String file = Objects.toString(result.get("fileName"), null);
    Integer version = number(result.get("version"));
    switch (status) {
      case "NOT_PUBLISHED" -> {
        if (!imports(ws).stream().anyMatch(r -> sourceId.equals(r.get("sourceId").toString()))) return;
        tx.executeWithoutResult(s -> {
          lock(ws);
          var counts = apply(ws, sourceId, null, List.of(), List.of(), null);
          record(ws, sourceId, null, null, "REMOVED", 0, 0, 0,
              "File removed: " + counts[1] + " unit(s) taken off the market");
        });
      }
      case "QUEUED" -> record(ws, sourceId, version, file, "PENDING", 0, 0, 0, "Reading the file");
      case "FAILED" -> record(ws, sourceId, version, file, "FAILED", 0, 0, 0,
          "Could not read the file: " + Objects.toString(result.get("error"), "unknown error"));
      case "DONE" -> {
        Map<String, Object> extraction = map(result.get("extraction"));
        tx.executeWithoutResult(s -> {
          lock(ws);
          int[] c = apply(ws, sourceId, file, list(extraction.get("projects")), list(extraction.get("listings")),
              Objects.toString(extraction.get("city"), null));
          boolean empty = c[0] == 0 && c[1] == 0;
          record(ws, sourceId, version, file, empty ? "EMPTY" : "IMPORTED", c[0], c[1], c[2],
              empty ? "No properties with a price in this file" : summary(c, extraction));
        });
      }
      default -> log.warn("Inventory import: source {} returned status {}", sourceId, status);
    }
  }

  private static String summary(int[] c, Map<String, Object> extraction) {
    String text = c[0] + " project(s), " + c[1] + " unit(s)" + (c[2] > 0 ? ", " + c[2] + " skipped (no area)" : "");
    List<?> warnings = extraction.get("warnings") instanceof List<?> w ? w : List.of();
    return warnings.isEmpty() ? text : text + "; " + warnings.size() + " value(s) not on the page were left out";
  }

  // ------------------------------------------------------------------ apply

  /**
   * Makes this file's contribution exactly {@code listings}: creates or updates their projects and
   * units, and withdraws what the file no longer contains. Returns {projects, units, skipped}.
   */
  int[] apply(Long ws, String sourceId, String fileName, List<Map<String, Object>> projects,
      List<Map<String, Object>> listings, String city) {
    Map<String, Map<String, Object>> projectInfo = new HashMap<>();
    for (var p : projects) {
      String name = text(p.get("name"));
      if (name != null) projectInfo.put(name.toLowerCase(Locale.ROOT), p);
    }
    Map<String, Long> projectIds = new LinkedHashMap<>();
    Set<String> unitKeys = new HashSet<>();
    int units = 0, skipped = 0;

    // A named project in the file is imported even before any of its units has a price.
    for (var p : projects) {
      String name = text(p.get("name"));
      if (name != null) projectIds.computeIfAbsent("project:" + name.toLowerCase(Locale.ROOT),
          key -> upsertProject(ws, key, name, p, null, city, sourceId, fileName));
    }
    for (var l : listings) {
      BigDecimal area = decimal(l.get("areaSqft"));
      BigDecimal price = decimal(l.get("priceInr"));
      if (price == null || price.signum() < 0) continue;
      String projectName = text(l.get("projectName"));
      String locality = text(l.get("locality"));
      String listingCity = Optional.ofNullable(text(l.get("city"))).orElse(city);
      String projectKey;
      String name;
      if (projectName != null) {
        projectKey = "project:" + projectName.toLowerCase(Locale.ROOT);
        name = projectName;
      } else if (locality != null) {
        projectKey = "locality:" + locality.toLowerCase(Locale.ROOT) + "|"
            + Objects.toString(listingCity, "").toLowerCase(Locale.ROOT);
        name = locality + " listings";
      } else {
        skipped++;
        continue;
      }
      if (area == null || area.signum() <= 0) {
        skipped++; // the CRM needs an area for every unit; the knowledge base still answers about it
        continue;
      }
      String finalName = name;
      Long projectId = projectIds.computeIfAbsent(projectKey, key -> upsertProject(ws, key, finalName,
          projectName == null ? null : projectInfo.get(projectName.toLowerCase(Locale.ROOT)),
          locality, listingCity, sourceId, fileName));
      String ref = text(l.get("ref"));
      String unitKey = ref != null ? "ref:" + ref.toLowerCase(Locale.ROOT)
          : "row:" + projectKey + "|" + Objects.toString(text(l.get("configuration")), "").toLowerCase(Locale.ROOT)
              + "|" + price.toPlainString() + "|" + area.toPlainString();
      if (!unitKeys.add(unitKey)) continue;
      upsertUnit(ws, projectId, unitKey, l, price, area, sourceId, fileName);
      units++;
    }
    withdraw(ws, sourceId, unitKeys, new HashSet<>(projectIds.values()));
    return new int[] {projectIds.size(), units, skipped};
  }

  private Long upsertProject(Long ws, String key, String name, Map<String, Object> info, String locality,
      String city, String sourceId, String fileName) {
    var existing = db.query(
        "SELECT id, status, data::text AS data FROM projects WHERE workspace_id=:ws AND"
            + " (data->>'importKey'=:key OR (lower(name)=lower(:name) AND status<>'ARCHIVED'))"
            + " ORDER BY (data->>'importKey'=:key) DESC NULLS LAST, id LIMIT 1",
        Map.of("ws", ws, "key", key, "name", name),
        (rs, n) -> new Object[] {rs.getLong("id"), rs.getString("status"), read(rs.getString("data"))});
    String location = info != null && text(info.get("location")) != null ? text(info.get("location"))
        : String.join(", ", new ArrayList<>(new LinkedHashSet<>(
            java.util.stream.Stream.of(locality, city).filter(Objects::nonNull).toList())));
    if (existing.isEmpty()) {
      Map<String, Object> data = new LinkedHashMap<>();
      data.put("description", info != null && text(info.get("description")) != null ? text(info.get("description"))
          : "Properties in " + location + ", imported from File management.");
      data.put("location", location.isBlank() ? name : location);
      fillProjectFacts(data, info);
      data.put("importKey", key);
      data.put("importCreated", true);
      data.put("importSources", new ArrayList<>(List.of(sourceId)));
      data.put("importedFiles", fileName == null ? new ArrayList<>() : new ArrayList<>(List.of(fileName)));
      return db.queryForObject(
          "INSERT INTO projects(workspace_id,name,status,data) VALUES (:ws,:name,'ACTIVE',CAST(:data AS jsonb))"
              + " RETURNING id",
          Map.of("ws", ws, "name", name.length() > 200 ? name.substring(0, 200) : name, "data", write(data)),
          Long.class);
    }
    Long id = (Long) existing.getFirst()[0];
    String status = (String) existing.getFirst()[1];
    @SuppressWarnings("unchecked") Map<String, Object> data = (Map<String, Object>) existing.getFirst()[2];
    addTo(data, "importSources", sourceId);
    if (fileName != null) addTo(data, "importedFiles", fileName);
    data.putIfAbsent("importKey", key);
    // Fill what is missing; never overwrite what someone typed into the CRM.
    Map<String, Object> facts = new LinkedHashMap<>();
    fillProjectFacts(facts, info);
    facts.forEach((k, v) -> { if (blank(data.get(k))) data.put(k, v); });
    boolean reactivate = "INACTIVE".equals(status) && Boolean.TRUE.equals(data.remove("importDeactivated"));
    db.update("UPDATE projects SET data=CAST(:data AS jsonb), status=:status, updated_at=now()"
            + " WHERE workspace_id=:ws AND id=:id",
        Map.of("data", write(data), "status", reactivate ? "ACTIVE" : status, "ws", ws, "id", id));
    return id;
  }

  private void fillProjectFacts(Map<String, Object> data, Map<String, Object> info) {
    if (info == null) return;
    putText(data, "developer", info.get("developer"), 200);
    putText(data, "reraId", info.get("reraId"), 120);
    String possession = text(info.get("possession"));
    if (possession != null) {
      data.put("possession", possession);
      LocalDate date = possessionDate(possession);
      if (date != null) data.put("possessionDate", date.toString());
    }
    if (info.get("amenities") instanceof List<?> amenities && !amenities.isEmpty())
      data.put("amenities", String.join(", ", amenities.stream().map(String::valueOf).toList()));
  }

  static LocalDate possessionDate(String text) {
    String t = text.trim().replaceAll("(?i)^(by|from|in|possession:?)\\s+", "").replaceAll("[,.]", " ").replaceAll("\\s+", " ").trim();
    try {
      return YearMonth.parse(t, MONTH_YEAR).atDay(1);
    } catch (RuntimeException e) {
      var year = java.util.regex.Pattern.compile("\\b(20\\d\\d)\\b").matcher(t);
      var quarter = java.util.regex.Pattern.compile("(?i)\\bQ([1-4])\\b").matcher(t);
      if (year.find()) return LocalDate.of(Integer.parseInt(year.group(1)), quarter.find() ? (Integer.parseInt(quarter.group(1)) - 1) * 3 + 1 : 12, 1);
      return null;
    }
  }

  private void upsertUnit(Long ws, Long projectId, String key, Map<String, Object> l, BigDecimal price,
      BigDecimal area, String sourceId, String fileName) {
    var existing = db.query(
        "SELECT id, project_id, status, unit_number, data::text AS data FROM units"
            + " WHERE workspace_id=:ws AND data->>'importKey'=:key LIMIT 1",
        Map.of("ws", ws, "key", key),
        (rs, n) -> new Object[] {rs.getLong("id"), rs.getLong("project_id"), rs.getString("status"),
            rs.getString("unit_number"), read(rs.getString("data"))});
    String transaction = "RENT".equals(l.get("transaction")) ? "RENT" : "SALE";
    int bhk = Math.max(0, Math.min(20, Optional.ofNullable(number(l.get("bhk"))).orElse(0)));
    String type = Optional.ofNullable(text(l.get("propertyType")))
        .orElse(bhk > 0 ? "Apartment" : Optional.ofNullable(text(l.get("configuration"))).orElse("Other"));
    Map<String, Object> facts = new LinkedHashMap<>();
    for (String field : List.of("configuration", "propertyType", "furnishing", "facing", "parking",
        "availability", "notes", "priceText", "locality"))
      if (text(l.get(field)) != null) facts.put(field, text(l.get(field)));
    if (l.get("amenities") instanceof List<?> amenities && !amenities.isEmpty()) facts.put("amenities", amenities);

    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws); params.put("project", projectId); params.put("price", price); params.put("area", area);
    params.put("bhk", bhk); params.put("type", type.length() > 40 ? type.substring(0, 40) : type);
    params.put("transaction", transaction);
    if (existing.isEmpty()) {
      Map<String, Object> data = new LinkedHashMap<>(facts);
      data.put("importKey", key);
      data.put("importSources", new ArrayList<>(List.of(sourceId)));
      data.put("importedFiles", fileName == null ? new ArrayList<>() : new ArrayList<>(List.of(fileName)));
      params.put("data", write(data));
      params.put("number", unitNumber(ws, projectId, label(l), null));
      db.update("INSERT INTO units(workspace_id,project_id,unit_number,status,price,area,bhk,property_type,"
              + "transaction_type,data) VALUES (:ws,:project,:number,'AVAILABLE',:price,:area,:bhk,:type,"
              + ":transaction,CAST(:data AS jsonb))", params);
      return;
    }
    Object[] row = existing.getFirst();
    @SuppressWarnings("unchecked") Map<String, Object> data = (Map<String, Object>) row[4];
    data.putAll(facts);
    addTo(data, "importSources", sourceId);
    if (fileName != null) addTo(data, "importedFiles", fileName);
    // Back on the market only if the import took it off; a SOLD or RESERVED mark stays.
    String status = (String) row[2];
    if ("UNAVAILABLE".equals(status) && Boolean.TRUE.equals(data.remove("importRemoved"))) status = "AVAILABLE";
    boolean moved = !projectId.equals(row[1]);
    params.put("id", row[0]);
    params.put("status", status);
    params.put("data", write(data));
    params.put("number", moved ? unitNumber(ws, projectId, label(l), (Long) row[0]) : row[3]);
    db.update("UPDATE units SET project_id=:project, unit_number=:number, status=:status, price=:price, area=:area,"
        + " bhk=:bhk, property_type=:type, transaction_type=:transaction, data=CAST(:data AS jsonb),"
        + " updated_at=now() WHERE workspace_id=:ws AND id=:id", params);
  }

  private static String label(Map<String, Object> l) {
    String label = Optional.ofNullable(text(l.get("ref")))
        .or(() -> Optional.ofNullable(text(l.get("configuration"))))
        .or(() -> Optional.ofNullable(text(l.get("propertyType")))).orElse("Unit");
    return label.length() > 54 ? label.substring(0, 54) : label;
  }

  /** Unit numbers are unique within a project: a second "2 BHK" becomes "2 BHK #2". */
  private String unitNumber(Long ws, Long projectId, String label, Long self) {
    for (int n = 1; n < 1000; n++) {
      String candidate = n == 1 ? label : label + " #" + n;
      Integer taken = db.queryForObject(
          "SELECT count(*) FROM units WHERE project_id=:project AND lower(unit_number)=lower(:number)"
              + " AND id<>:self",
          Map.of("project", projectId, "number", candidate, "self", self == null ? -1L : self), Integer.class);
      if (taken == null || taken == 0) return candidate;
    }
    return label + " #" + UUID.randomUUID().toString().substring(0, 6);
  }

  /** What this file no longer contains loses it as a source; with no source left it comes off the market. */
  private void withdraw(Long ws, String sourceId, Set<String> keepUnits, Set<Long> keepProjects) {
    var units = db.query(
        "SELECT id, status, data::text AS data FROM units WHERE workspace_id=:ws"
            + " AND data->'importSources' @> jsonb_build_array(CAST(:source AS text))",
        Map.of("ws", ws, "source", sourceId),
        (rs, n) -> new Object[] {rs.getLong("id"), rs.getString("status"), read(rs.getString("data"))});
    for (Object[] u : units) {
      @SuppressWarnings("unchecked") Map<String, Object> data = (Map<String, Object>) u[2];
      if (keepUnits.contains(data.get("importKey"))) continue;
      List<Object> sources = sources(data);
      sources.remove(sourceId);
      String status = (String) u[1];
      if (sources.isEmpty() && "AVAILABLE".equals(status)) {
        status = "UNAVAILABLE";
        data.put("importRemoved", true);
      }
      db.update("UPDATE units SET data=CAST(:data AS jsonb), status=:status, updated_at=now()"
          + " WHERE workspace_id=:ws AND id=:id", Map.of("data", write(data), "status", status, "ws", ws, "id", u[0]));
    }
    var projects = db.query(
        "SELECT id, status, data::text AS data FROM projects WHERE workspace_id=:ws"
            + " AND data->'importSources' @> jsonb_build_array(CAST(:source AS text))",
        Map.of("ws", ws, "source", sourceId),
        (rs, n) -> new Object[] {rs.getLong("id"), rs.getString("status"), read(rs.getString("data"))});
    for (Object[] p : projects) {
      if (keepProjects.contains((Long) p[0])) continue;
      @SuppressWarnings("unchecked") Map<String, Object> data = (Map<String, Object>) p[2];
      List<Object> sources = sources(data);
      sources.remove(sourceId);
      String status = (String) p[1];
      Integer available = db.queryForObject(
          "SELECT count(*) FROM units WHERE workspace_id=:ws AND project_id=:id AND status='AVAILABLE'",
          Map.of("ws", ws, "id", p[0]), Integer.class);
      // Only a project the import created is retired; one created in the CRM stays as it is.
      boolean createdByImport = Boolean.TRUE.equals(data.get("importCreated"));
      if (sources.isEmpty() && createdByImport && "ACTIVE".equals(status) && (available == null || available == 0)) {
        status = "INACTIVE";
        data.put("importDeactivated", true);
      }
      db.update("UPDATE projects SET data=CAST(:data AS jsonb), status=:status, updated_at=now()"
          + " WHERE workspace_id=:ws AND id=:id", Map.of("data", write(data), "status", status, "ws", ws, "id", p[0]));
    }
  }

  // ------------------------------------------------------------------ status

  public List<Map<String, Object>> imports(Long ws) {
    return db.query(
        "SELECT source_id, version, file_name, status, projects, units, skipped, message, updated_at"
            + " FROM knowledge_imports WHERE workspace_id=:ws ORDER BY updated_at DESC",
        Map.of("ws", ws),
        (rs, n) -> {
          Map<String, Object> row = new LinkedHashMap<>();
          row.put("sourceId", rs.getString("source_id"));
          row.put("version", rs.getObject("version"));
          row.put("fileName", rs.getString("file_name"));
          row.put("status", rs.getString("status"));
          row.put("projects", rs.getInt("projects"));
          row.put("units", rs.getInt("units"));
          row.put("skipped", rs.getInt("skipped"));
          row.put("message", rs.getString("message"));
          row.put("updatedAt", rs.getTimestamp("updated_at").toInstant().toString());
          return row;
        });
  }

  private void record(Long ws, String sourceId, Integer version, String file, String status, int projects,
      int units, int skipped, String message) {
    Map<String, Object> p = new HashMap<>();
    p.put("ws", ws); p.put("source", UUID.fromString(sourceId)); p.put("version", version); p.put("file", file);
    p.put("status", status); p.put("projects", projects); p.put("units", units); p.put("skipped", skipped);
    p.put("message", message == null || message.length() <= 1000 ? message : message.substring(0, 1000));
    db.update("INSERT INTO knowledge_imports(workspace_id,source_id,version,file_name,status,projects,units,skipped,message)"
        + " VALUES (:ws,:source,:version,:file,:status,:projects,:units,:skipped,:message)"
        + " ON CONFLICT (workspace_id, source_id) DO UPDATE SET version=coalesce(EXCLUDED.version, knowledge_imports.version),"
        + " file_name=coalesce(EXCLUDED.file_name, knowledge_imports.file_name), status=EXCLUDED.status,"
        + " projects=EXCLUDED.projects, units=EXCLUDED.units, skipped=EXCLUDED.skipped, message=EXCLUDED.message,"
        + " updated_at=now()", p);
  }

  // ------------------------------------------------------------------ helpers

  private void lock(Long ws) {
    db.getJdbcTemplate().queryForObject("SELECT pg_advisory_xact_lock(?)", Object.class, ws);
  }

  @SuppressWarnings("unchecked")
  private static List<Object> sources(Map<String, Object> data) {
    Object value = data.get("importSources");
    List<Object> list = value instanceof List<?> l ? new ArrayList<>((List<Object>) l) : new ArrayList<>();
    data.put("importSources", list);
    return list;
  }

  private static void addTo(Map<String, Object> data, String key, String value) {
    List<Object> list = data.get(key) instanceof List<?> l ? new ArrayList<>(l) : new ArrayList<>();
    if (!list.contains(value)) list.add(value);
    data.put(key, list);
  }

  private static void putText(Map<String, Object> data, String key, Object value, int max) {
    String t = text(value);
    if (t != null) data.put(key, t.length() > max ? t.substring(0, max) : t);
  }

  private static boolean blank(Object value) {
    return value == null || value.toString().isBlank();
  }

  private static String text(Object value) {
    if (value == null) return null;
    String t = value.toString().trim();
    return t.isEmpty() || t.equalsIgnoreCase("null") ? null : t;
  }

  private static Integer number(Object value) {
    if (value instanceof Number n) return n.intValue();
    try { return value == null ? null : Integer.valueOf(value.toString()); } catch (NumberFormatException e) { return null; }
  }

  private static BigDecimal decimal(Object value) {
    if (value == null) return null;
    try { return new BigDecimal(value.toString()); } catch (NumberFormatException e) { return null; }
  }

  @SuppressWarnings("unchecked")
  private static List<Map<String, Object>> list(Object value) {
    if (!(value instanceof List<?> l)) return List.of();
    return l.stream().filter(Map.class::isInstance).map(v -> (Map<String, Object>) v).toList();
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> map(Object value) {
    return value instanceof Map<?, ?> m ? (Map<String, Object>) m : Map.of();
  }

  private Map<String, Object> read(String text) {
    try { return text == null ? new LinkedHashMap<>() : new LinkedHashMap<>(json.readValue(text, MAP)); }
    catch (Exception e) { return new LinkedHashMap<>(); }
  }

  private String write(Object value) {
    try { return json.writeValueAsString(value); }
    catch (Exception e) { throw new IllegalStateException("could not serialise import data", e); }
  }
}
