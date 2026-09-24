package com.estateos.service;

import com.estateos.audit.AuditService;
import com.estateos.dto.*;
import com.estateos.exception.ApiException;
import com.estateos.integration.*;
import com.estateos.mapper.DtoMapper;
import com.estateos.repository.TenantRepository;
import com.estateos.security.TenantContext;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EstateService {
  private final TenantRepository repo;
  private final TenantContext tenant;
  private final DtoMapper mapper;
  private final AuditService audit;
  private final RagServiceClient rag;
  private final VoiceAgentServiceClient voice;
  private final NotificationServiceClient notification;
  private final String countryCode;
  private static final Set<String> MANAGED =
      Set.of(
          "projects",
          "units",
          "buildings",
          "floors",
          "unit_types",
          "property_documents",
          "amenities");

  public EstateService(
      TenantRepository repo,
      TenantContext tenant,
      DtoMapper mapper,
      AuditService audit,
      RagServiceClient rag,
      VoiceAgentServiceClient voice,
      NotificationServiceClient notification,
      @org.springframework.beans.factory.annotation.Value("${app.default-country-code:91}")
          String countryCode) {
    this.repo = repo;
    this.tenant = tenant;
    this.mapper = mapper;
    this.audit = audit;
    this.rag = rag;
    this.voice = voice;
    this.notification = notification;
    if (!countryCode.matches("[0-9]{1,4}"))
      throw new IllegalStateException("DEFAULT_COUNTRY_CODE must be 1 to 4 digits");
    this.countryCode = countryCode;
  }

  public static Long id(Object value) {
    if (value == null || value.toString().isBlank()) return null;
    Long id = Long.valueOf(value.toString());
    if (id <= 0) throw ApiException.bad("ID must be positive");
    return id;
  }

  public static Map<String, Object> fields(Object... pairs) {
    Map<String, Object> out = new LinkedHashMap<>();
    for (int i = 0; i < pairs.length; i += 2) out.put(pairs[i].toString(), pairs[i + 1]);
    return out;
  }

  private String string(Map<String, Object> data, String key, String fallback) {
    Object value = data.get(key);
    return value == null || value.toString().isBlank() ? fallback : value.toString().trim();
  }

  private String status(String value, String fallback, String... allowed) {
    String v = value == null || value.isBlank() ? fallback : value;
    if (!Set.of(allowed).contains(v)) throw ApiException.bad("Unsupported status: " + v);
    return v;
  }

  private String language(String value) {
    String v = value == null || value.isBlank() ? "en" : value;
    if (!Set.of("en", "hi", "gu", "mr").contains(v))
      throw ApiException.bad("Language must be en, hi, gu or mr");
    return v;
  }

  private void ranges(BigDecimal min, BigDecimal max, String label) {
    if (min != null && max != null && min.compareTo(max) > 0)
      throw ApiException.bad(label + " minimum cannot exceed maximum");
  }

  private void project(Long ws, Long project) {
    repo.get("projects", ws, project);
  }

  private void permission(String table, Long ws) {
    if (MANAGED.contains(table)) tenant.manage(ws);
    else tenant.require(ws);
  }

  public PageResponse<Map<String, Object>> list(
      String table, Long ws, Map<String, String> filters) {
    tenant.require(ws);
    if (table.equals("audit_logs")) tenant.manage(ws);
    if (table.equals("notifications")) {
      filters = new HashMap<>(filters);
      filters.put("recipientUserId", tenant.user().toString());
    }
    return repo.list(table, ws, filters);
  }

  public Map<String, Object> get(String table, Long ws, Long resource) {
    tenant.require(ws);
    Map<String, Object> result = new LinkedHashMap<>(repo.get(table, ws, resource));
    if (table.equals("leads")) {
      result.put("activities", repo.related("lead_activities", ws, "lead_id", resource));
      result.put("notesHistory", repo.related("lead_notes", ws, "lead_id", resource));
      result.put("calls", repo.related("voice_sessions", ws, "lead_id", resource));
      result.put("siteVisits", repo.related("appointments", ws, "lead_id", resource));
      result.put("handovers", repo.related("handover_records", ws, "lead_id", resource));
      result.put("recommendations", suggestions(ws, resource));
    }
    if (table.equals("handover_records")) {
      Long lead = id(result.get("leadId"));
      result.put("lead", repo.get("leads", ws, lead));
      result.put("calls", repo.related("voice_sessions", ws, "lead_id", lead));
      result.put("siteVisits", repo.related("appointments", ws, "lead_id", lead));
      result.put("recommendations", suggestions(ws, lead));
    }
    return result;
  }

  public List<Map<String, Object>> related(
      String table, Long ws, String column, Long parent, String parentTable) {
    tenant.require(ws);
    repo.get(parentTable, ws, parent);
    return repo.related(table, ws, column, parent);
  }

  private void event(Long ws, String action, String type, Long resource) {
    audit.record(ws, tenant.user(), action, type, resource);
  }

  private void activity(Long ws, Long lead, String action, String detail) {
    repo.event(
        "lead_activities",
        ws,
        "lead_id",
        lead,
        fields("action", action, "description", detail, "userId", tenant.user()));
  }

  @Transactional
  public Map<String, Object> saveProject(Long ws, Long resource, Requests.Project request) {
    tenant.manage(ws);
    repo.workspaceLock(ws);
    if (resource != null) repo.get("projects", ws, resource);
    Map<String, Object> data = mapper.map(request);
    String state =
        status(request.status(), "ACTIVE", "ACTIVE", "INACTIVE", "COMPLETED", "ARCHIVED");
    if (request.mediaUrl() != null
        && !request.mediaUrl().isBlank()
        && !request.mediaUrl().matches("https?://[^\\s]+"))
      throw ApiException.bad("Media URL must use http or https");
    var saved =
        repo.save(
            "projects", ws, resource, data, fields("name", request.name().trim(), "status", state));
    Long uuid = id(saved.get("id"));
    repo.event("project_locations", ws, "project_id", uuid, fields("location", request.location()));
    repo.event(
        "project_amenities", ws, "project_id", uuid, fields("amenities", request.amenities()));
    event(ws, resource == null ? "PROJECT_CREATED" : "PROJECT_UPDATED", "PROJECT", uuid);
    return saved;
  }

  @Transactional
  public Map<String, Object> saveUnit(Long ws, Long resource, Requests.Unit request) {
    tenant.manage(ws);
    repo.workspaceLock(ws);
    project(ws, request.projectId());
    if (request.buildingId() != null) {
      var building = repo.get("buildings", ws, request.buildingId());
      if (!request.projectId().equals(id(building.get("projectId"))))
        throw ApiException.bad("Building belongs to another project");
    }
    Map<String, Object> old = resource == null ? null : repo.get("units", ws, resource);
    String state =
        status(
            request.status(),
            "AVAILABLE",
            "AVAILABLE",
            "RESERVED",
            "SOLD",
            "BLOCKED",
            "UNAVAILABLE");
    var saved =
        repo.save(
            "units",
            ws,
            resource,
            mapper.map(request),
            fields(
                "project_id",
                request.projectId(),
                "building_id",
                request.buildingId(),
                "unit_number",
                request.unitNumber().trim(),
                "status",
                state,
                "price",
                request.price(),
                "area",
                request.area(),
                "bhk",
                request.bhk(),
                "property_type",
                request.propertyType().toUpperCase(Locale.ROOT)));
    Long uuid = id(saved.get("id"));
    if (old == null || !old.get("status").equals(state))
      repo.event(
          "unit_status_history",
          ws,
          "unit_id",
          uuid,
          fields(
              "previousStatus",
              old == null ? null : old.get("status"),
              "status",
              state,
              "userId",
              tenant.user()));
    repo.event(
        "unit_prices", ws, "unit_id", uuid, fields("price", request.price(), "currency", "INR"));
    event(ws, resource == null ? "UNIT_CREATED" : "UNIT_UPDATED", "UNIT", uuid);
    return saved;
  }

  @Transactional
  public Map<String, Object> saveBuilding(
      Long ws, Long project, Requests.Building request, String table) {
    tenant.manage(ws);
    project(ws, project);
    return repo.save(
        table,
        ws,
        null,
        mapper.map(request),
        fields("project_id", project, "name", request.name().trim()));
  }

  @Transactional
  public Map<String, Object> saveFloor(Long ws, Long project, Requests.Floor request) {
    tenant.manage(ws);
    project(ws, project);
    var building = repo.get("buildings", ws, request.buildingId());
    if (!project.equals(id(building.get("projectId"))))
      throw ApiException.bad("Building belongs to another project");
    return repo.save(
        "floors",
        ws,
        null,
        mapper.map(request),
        fields(
            "project_id",
            project,
            "building_id",
            request.buildingId(),
            "number",
            request.number()));
  }

  @Transactional
  public Map<String, Object> saveAmenity(Long ws, Requests.Building request) {
    tenant.manage(ws);
    return repo.save("amenities", ws, null, mapper.map(request), Map.of());
  }

  @Transactional
  public Map<String, Object> saveLead(Long ws, Long resource, Requests.Lead request) {
    tenant.require(ws);
    ranges(request.budgetMin(), request.budgetMax(), "Budget");
    ranges(request.areaMin(), request.areaMax(), "Area");
    tenant.member(ws, request.assignedAgentId());
    String phone = "+" + request.phone().replaceAll("[^0-9]", "");
    if (!phone.matches("\\+?[0-9]{7,15}"))
      throw ApiException.bad("Phone must contain 7 to 15 digits and optional leading +");
    String email =
        request.email() == null || request.email().isBlank()
            ? null
            : request.email().trim().toLowerCase(Locale.ROOT);
    String state =
        status(
            request.status(),
            "NEW",
            "NEW",
            "CONTACTED",
            "QUALIFIED",
            "VISIT_PLANNED",
            "VISIT_COMPLETED",
            "HANDED_OVER",
            "NOT_INTERESTED",
            "LOST");
    Map<String, Object> data = mapper.map(request);
    data.put("language", language(request.language()));
    data.put("intent", status(request.intent(), "BUY", "BUY", "RENT"));
    Map<String, Object> old = resource == null ? null : repo.get("leads", ws, resource);
    var saved =
        repo.save(
            "leads",
            ws,
            resource,
            data,
            fields(
                "name",
                request.name().trim(),
                "phone",
                phone,
                "email",
                email,
                "status",
                state,
                "assigned_agent_id",
                request.assignedAgentId()));
    Long uuid = id(saved.get("id"));
    repo.event("lead_preferences", ws, "lead_id", uuid, data);
    repo.event("lead_contacts", ws, "lead_id", uuid, fields("phone", phone, "email", email));
    repo.event("lead_tags", ws, "lead_id", uuid, fields("tags", request.tags()));
    if (old == null || !old.get("status").equals(state))
      repo.event(
          "lead_status_history",
          ws,
          "lead_id",
          uuid,
          fields("status", state, "previousStatus", old == null ? null : old.get("status")));
    if (request.assignedAgentId() != null
        && (old == null || !request.assignedAgentId().equals(id(old.get("assignedAgentId"))))) {
      repo.event(
          "lead_assignments", ws, "lead_id", uuid, fields("agentId", request.assignedAgentId()));
      event(ws, "LEAD_ASSIGNED", "LEAD", uuid);
      notify(
          ws,
          request.assignedAgentId(),
          "AGENT_ASSIGNMENT",
          "A lead has been assigned to you",
          uuid);
    }
    scheduleReminder(
        ws,
        request.assignedAgentId() == null ? tenant.user() : request.assignedAgentId(),
        "CALLBACK_REMINDER",
        uuid,
        request.followUpAt(),
        "Follow up with " + request.name());
    activity(ws, uuid, resource == null ? "LEAD_CREATED" : "LEAD_UPDATED", "Lead profile saved");
    event(ws, resource == null ? "LEAD_CREATED" : "LEAD_UPDATED", "LEAD", uuid);
    return saved;
  }

  @Transactional
  public Map<String, Object> note(Long ws, Long lead, Requests.Note request) {
    tenant.require(ws);
    repo.get("leads", ws, lead);
    var result =
        repo.event(
            "lead_notes",
            ws,
            "lead_id",
            lead,
            fields("text", request.text(), "userId", tenant.user()));
    activity(ws, lead, "NOTE_ADDED", "A note was added");
    event(ws, "LEAD_NOTE_ADDED", "LEAD", lead);
    return result;
  }

  @Transactional
  public Map<String, Object> document(Long ws, Requests.Document request) {
    tenant.manage(ws);
    project(ws, request.projectId());
    if (!request.fileName().toLowerCase(Locale.ROOT).endsWith(".pdf"))
      throw ApiException.bad("Only PDF document metadata is supported");
    Map<String, Object> data = mapper.map(request);
    data.put("language", language(request.language()));
    data.put("processingStatus", "NOT_INDEXED");
    data.put("version", 1);
    data.put("storageMode", "EXTERNAL_REFERENCE");
    var result =
        repo.save(
            "property_documents",
            ws,
            null,
            data,
            fields(
                "project_id",
                request.projectId(),
                "title",
                request.title().trim(),
                "status",
                "DRAFT"));
    Long uuid = id(result.get("id"));
    repo.save(
        "files",
        ws,
        null,
        fields(
            "documentId",
            uuid,
            "fileName",
            request.fileName(),
            "storageReference",
            request.storageReference(),
            "contentType",
            "application/pdf"),
        fields("project_id", request.projectId()));
    version(ws, uuid, result);
    repo.event(
        "property_document_versions",
        ws,
        "document_id",
        uuid,
        fields(
            "fileName",
            request.fileName(),
            "storageReference",
            request.storageReference(),
            "version",
            1));
    event(ws, "DOCUMENT_REGISTERED", "DOCUMENT", uuid);
    return result;
  }

  private void version(Long ws, Long doc, Map<String, Object> data) {
    repo.event(
        "property_content_versions",
        ws,
        "document_id",
        doc,
        fields(
            "version",
            data.get("version"),
            "content",
            data.get("content"),
            "language",
            data.get("language"),
            "pageReference",
            data.get("pageReference"),
            "status",
            data.get("status"),
            "userId",
            tenant.user()));
    repo.event(
        "property_content",
        ws,
        "document_id",
        doc,
        fields(
            "version",
            data.get("version"),
            "content",
            data.get("content"),
            "status",
            data.get("status")));
  }

  private Map<String, Object> docPayload(Long ws, Map<String, Object> document) {
    Map<String, Object> payload = new LinkedHashMap<>(document);
    payload.put("workspaceId", ws.toString());
    payload.put("documentId", document.get("id"));
    payload.put("resourceId", document.get("id"));
    return payload;
  }

  @Transactional(noRollbackFor = ExternalServiceException.class)
  public Map<String, Object> content(Long ws, Long doc, Requests.Content request) {
    tenant.manage(ws);
    String normalizedLanguage = language(request.language());
    repo.workspaceLock(ws);
    var data = new LinkedHashMap<>(repo.get("property_documents", ws, doc));
    if (data.get("status").equals("PUBLISHED")) {
      try {
        rag.unpublishContent(docPayload(ws, data));
      } catch (ExternalServiceException e) {
        event(ws, "EXTERNAL_SERVICE_FAILED", "DOCUMENT", doc);
        throw e;
      }
    }
    data.putAll(mapper.map(request));
    data.put("language", normalizedLanguage);
    data.put("version", ((Number) data.getOrDefault("version", 1)).intValue() + 1);
    data.put("status", "DRAFT");
    data.put("processingStatus", "NOT_INDEXED");
    var result = repo.save("property_documents", ws, doc, data, fields("status", "DRAFT"));
    version(ws, doc, result);
    event(ws, "CONTENT_EDITED", "DOCUMENT", doc);
    return result;
  }

  @Transactional(noRollbackFor = ExternalServiceException.class)
  public Map<String, Object> documentAction(Long ws, Long doc, String action) {
    tenant.manage(ws);
    repo.workspaceLock(ws);
    var data = new LinkedHashMap<>(repo.get("property_documents", ws, doc));
    try {
      Map<String, Object> result;
      if (action.equals("unpublish")) {
        result = rag.unpublishContent(docPayload(ws, data));
        data.put("status", "DRAFT");
        data.put("processingStatus", "NOT_INDEXED");
      } else {
        if (action.equals("reindex") && !data.get("status").equals("PUBLISHED"))
          throw ApiException.bad("Only published content can be reindexed");
        if (string(data, "content", "").isBlank())
          throw ApiException.bad("Add content before publishing");
        data.put("status", "PUBLISHED");
        var payload = docPayload(ws, data);
        payload.put("publishedOnly", true);
        result =
            action.equals("publish")
                ? rag.indexPublishedContent(payload)
                : rag.reindexDocument(payload);
        data.put("processingStatus", result.getOrDefault("status", "QUEUED"));
      }
      data.put("mock", result.getOrDefault("mock", false));
      data.put("processingError", null);
      var saved =
          repo.save("property_documents", ws, doc, data, fields("status", data.get("status")));
      version(ws, doc, saved);
      event(ws, "CONTENT_" + action.toUpperCase(Locale.ROOT), "DOCUMENT", doc);
      return saved;
    } catch (ExternalServiceException e) {
      data.put("processingStatus", "FAILED");
      data.put("processingError", e.getMessage());
      repo.save("property_documents", ws, doc, data, Map.of());
      event(ws, "EXTERNAL_SERVICE_FAILED", "DOCUMENT", doc);
      throw e;
    }
  }

  @Transactional(noRollbackFor = ExternalServiceException.class)
  public Map<String, Object> processing(Long ws, Long doc) {
    tenant.require(ws);
    var data = repo.get("property_documents", ws, doc);
    if (!data.get("status").equals("PUBLISHED"))
      return fields(
          "status",
          data.get("processingStatus"),
          "documentId",
          doc,
          "mock",
          data.getOrDefault("mock", false));
    try {
      return rag.getProcessingStatus(docPayload(ws, data));
    } catch (ExternalServiceException e) {
      event(ws, "EXTERNAL_SERVICE_FAILED", "DOCUMENT", doc);
      throw e;
    }
  }

  private List<Map<String, Object>> suggestions(Long ws, Long lead) {
    List<Map<String, Object>> out = new ArrayList<>();
    for (var r : repo.related("lead_recommendations", ws, "lead_id", lead)) {
      var unit = repo.get("units", ws, id(r.get("unitId")));
      out.add(
          fields(
              "unit",
              unit,
              "project",
              repo.get("projects", ws, id(unit.get("projectId"))),
              "reason",
              r.getOrDefault("reason", "Selected by agent")));
    }
    return out;
  }

  @Transactional(noRollbackFor = ExternalServiceException.class)
  public Map<String, Object> recommend(Long ws, Requests.Recommendation request) {
    tenant.require(ws);
    Map<String, Object> p = mapper.map(request);
    if (request.leadId() != null) {
      var lead = repo.get("leads", ws, request.leadId());
      for (String key :
          List.of(
              "budgetMin",
              "budgetMax",
              "location",
              "propertyType",
              "bhk",
              "areaMin",
              "areaMax",
              "language")) if (p.get(key) == null) p.put(key, lead.get(key));
    }
    if (request.projectId() != null) project(ws, request.projectId());
    ranges(decimal(p.get("budgetMin")), decimal(p.get("budgetMax")), "Budget");
    ranges(decimal(p.get("areaMin")), decimal(p.get("areaMax")), "Area");
    StringBuilder where =
        new StringBuilder(
            " WHERE u.workspace_id=:ws AND u.status='AVAILABLE' AND p.status='ACTIVE'");
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    for (String[] filter :
        new String[][] {
          {"budgetMin", "u.price>=:budgetMin"},
          {"budgetMax", "u.price<=:budgetMax"},
          {"areaMin", "u.area>=:areaMin"},
          {"areaMax", "u.area<=:areaMax"},
          {"bhk", "u.bhk=:bhk"}
        })
      if (p.get(filter[0]) != null) {
        where.append(" AND ").append(filter[1]);
        params.put(filter[0], decimal(p.get(filter[0])));
      }
    if (request.projectId() != null) {
      where.append(" AND u.project_id=:projectId");
      params.put("projectId", request.projectId());
    }
    if (!string(p, "location", "").isBlank()) {
      where.append(" AND p.data->>'location' ILIKE :location");
      params.put("location", "%" + string(p, "location", "") + "%");
    }
    if (!string(p, "propertyType", "").isBlank()) {
      where.append(" AND upper(u.property_type)=upper(:propertyType)");
      params.put("propertyType", string(p, "propertyType", ""));
    }
    var units =
        repo.sql()
            .query(
                "SELECT u.* FROM units u JOIN projects p ON p.workspace_id=u.workspace_id AND"
                    + " p.id=u.project_id"
                    + where
                    + " ORDER BY u.price,u.id LIMIT 100",
                params,
                repo::row);
    List<Map<String, Object>> matches = new ArrayList<>();
    for (var unit : units) {
      String reason =
          "Currently available; matches "
              + (params.size() > 1
                  ? "the supplied budget, location and property preferences"
                  : "available inventory")
              + ". Price ₹"
              + unit.get("price")
              + ", "
              + unit.get("bhk")
              + " BHK, "
              + unit.get("area")
              + " sq ft.";
      matches.add(
          fields(
              "unit",
              unit,
              "project",
              repo.get("projects", ws, id(unit.get("projectId"))),
              "reason",
              reason));
    }
    p.put("workspaceId", ws.toString());
    p.put("language", language(string(p, "language", "en")));
    p.put("publishedOnly", true);
    var published =
        repo.sql()
            .queryForList(
                "SELECT id FROM property_documents WHERE workspace_id=:ws AND status='PUBLISHED'"
                    + (request.projectId() == null ? "" : " AND project_id=:projectId"),
                request.projectId() == null
                    ? Map.of("ws", ws)
                    : Map.of("ws", ws, "projectId", request.projectId()),
                Long.class);
    p.put("publishedDocumentIds", published.stream().map(Object::toString).toList());
    Map<String, Object> knowledge = Map.of("results", List.of(), "mock", false);
    if (!string(p, "query", "").isBlank()) {
      try {
        knowledge = rag.searchKnowledgeBase(p);
      } catch (ExternalServiceException e) {
        event(ws, "EXTERNAL_SERVICE_FAILED", "KNOWLEDGE", request.projectId());
        throw e;
      }
    }
    return fields(
        "items",
        matches,
        "knowledge",
        knowledge.getOrDefault("results", List.of()),
        "mock",
        knowledge.getOrDefault("mock", false));
  }

  private BigDecimal decimal(Object value) {
    return value == null ? null : new BigDecimal(value.toString());
  }

  @Transactional
  public List<Map<String, Object>> saveSuggestions(
      Long ws, Long lead, Requests.Suggestions request) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    repo.get("leads", ws, lead);
    for (Long uuid : new LinkedHashSet<>(request.unitIds())) {
      var unit = repo.get("units", ws, uuid);
      if (!unit.get("status").equals("AVAILABLE"))
        throw ApiException.conflict("A selected unit is no longer available");
      var project = repo.get("projects", ws, id(unit.get("projectId")));
      if (!project.get("status").equals("ACTIVE"))
        throw ApiException.conflict("A selected project is inactive");
      repo.sql()
          .update(
              "INSERT INTO lead_recommendations(workspace_id,lead_id,unit_id,data) VALUES"
                  + " (:ws,:lead,:unit,'{\"reason\":\"Selected by agent\"}') ON"
                  + " CONFLICT(lead_id,unit_id) DO NOTHING",
              Map.of("ws", ws, "lead", lead, "unit", uuid));
    }
    activity(ws, lead, "PROPERTIES_RECOMMENDED", "Property suggestions saved");
    event(ws, "PROPERTIES_RECOMMENDED", "LEAD", lead);
    return suggestions(ws, lead);
  }

  @Transactional(noRollbackFor = ExternalServiceException.class)
  public Map<String, Object> call(Long ws, Requests.Call request, String key) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var lead = repo.get("leads", ws, request.leadId());
    if (key != null && (key.length() > 120 || !key.matches("[A-Za-z0-9_-]+")))
      throw ApiException.bad("Invalid Idempotency-Key");
    if (key != null) {
      var prior =
          repo.sql()
              .query(
                  "SELECT * FROM idempotency_keys WHERE workspace_id=:ws AND data->>'key'=:key",
                  Map.of("ws", ws, "key", key),
                  repo::row);
      if (!prior.isEmpty()) {
        if (!request.leadId().toString().equals(prior.getFirst().get("leadId")))
          throw ApiException.conflict("Idempotency key was used for another lead");
        return repo.get("voice_sessions", ws, id(prior.getFirst().get("callId")));
      }
    }
    String callId = java.util.UUID.randomUUID().toString();
    Map<String, Object> payload =
        fields(
            "workspaceId",
            ws.toString(),
            "leadId",
            request.leadId().toString(),
            "phone",
            lead.get("phone"),
            "language",
            lead.get("language"),
            "requestId",
            key == null ? callId.toString() : key);
    Map<String, Object> result;
    try {
      result = new LinkedHashMap<>(voice.startOutboundCall(payload));
    } catch (ExternalServiceException e) {
      event(ws, "EXTERNAL_SERVICE_FAILED", "LEAD", request.leadId());
      notify(
          ws,
          tenant.user(),
          "FAILED_CALL",
          "The outbound call could not be started",
          request.leadId());
      throw e;
    }
    result.put("leadName", lead.get("name"));
    var saved =
        repo.save(
            "voice_sessions",
            ws,
            null,
            result,
            fields("lead_id", request.leadId(), "status", result.getOrDefault("status", "QUEUED")));
    Long uuid = id(saved.get("id"));
    saveCallDetails(ws, uuid, result);
    if (key != null)
      repo.save(
          "idempotency_keys",
          ws,
          null,
          fields("key", key, "leadId", request.leadId().toString(), "callId", uuid),
          Map.of());
    activity(ws, request.leadId(), "CALL_STARTED", "Outbound call requested");
    event(ws, "CALL_STARTED", "VOICE_SESSION", uuid);
    return saved;
  }

  private void saveCallDetails(Long ws, Long uuid, Map<String, Object> result) {
    repo.event(
        "voice_session_events",
        ws,
        "voice_session_id",
        uuid,
        fields("status", result.get("status"), "outcome", result.get("outcome")));
    for (String[] pair :
        new String[][] {
          {"voice_transcripts", "transcript"},
          {"voice_summaries", "summary"},
          {"voice_session_requirements", "requirements"}
        })
      if (result.get(pair[1]) != null)
        repo.event(pair[0], ws, "voice_session_id", uuid, fields(pair[1], result.get(pair[1])));
  }

  /** Normalises a dialled number to E.164, assuming the configured country for a national number. */
  private String e164(String value) {
    String digits = value.replaceAll("[^0-9]", "");
    if (digits.length() == 10) digits = countryCode + digits;
    if (digits.length() < 7 || digits.length() > 15)
      throw ApiException.bad("Phone must contain 7 to 15 digits and optional leading +");
    return "+" + digits;
  }

  private static String tail(String phone) {
    String digits = phone.replaceAll("[^0-9]", "");
    return digits.length() <= 10 ? digits : digits.substring(digits.length() - 10);
  }

  /**
   * Resolves a caller's phone number to a lead, creating one on first contact. Used by the voice
   * agent at the start of a call, where the caller is known only by number. Serialized on the
   * workspace lock so two concurrent calls from the same number cannot create duplicate leads.
   */
  @Transactional
  public Map<String, Object> findOrCreateLead(Long ws, Requests.LeadLookup request) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    String phone = e164(request.phone());
    // Match on the last ten digits. The agent normalises callers to a national number while the
    // UI usually stores a country code, and matching the raw strings would split one person into
    // two leads.
    var existing =
        repo.sql()
            .query(
                "SELECT * FROM leads WHERE workspace_id=:ws AND"
                    + " right(regexp_replace(phone,'[^0-9]','','g'),10)=:tail ORDER BY id LIMIT 1",
                Map.of("ws", ws, "tail", tail(phone)),
                repo::row);
    if (!existing.isEmpty()) {
      Map<String, Object> found = new LinkedHashMap<>(existing.getFirst());
      found.put("created", false);
      return found;
    }
    if (request.projectId() != null) project(ws, request.projectId());
    String name =
        request.name() == null || request.name().isBlank()
            ? "Caller " + tail(phone).substring(6)
            : request.name().trim();
    Map<String, Object> data =
        fields(
            "language",
            language(request.language()),
            "intent",
            "BUY",
            "source",
            request.source() == null || request.source().isBlank()
                ? "VOICE_AGENT"
                : request.source().trim(),
            "campaign",
            request.campaign(),
            "projectId",
            request.projectId() == null ? null : request.projectId().toString(),
            "createdByVoiceAgent",
            true);
    var saved =
        repo.save(
            "leads",
            ws,
            null,
            data,
            fields("name", name, "phone", phone, "email", null, "status", "NEW"));
    Long uuid = id(saved.get("id"));
    repo.event("lead_contacts", ws, "lead_id", uuid, fields("phone", phone, "email", null));
    repo.event("lead_preferences", ws, "lead_id", uuid, data);
    repo.event(
        "lead_status_history", ws, "lead_id", uuid, fields("from", null, "to", "NEW"));
    activity(ws, uuid, "LEAD_CREATED", "Lead created from an inbound voice call");
    event(ws, "LEAD_CREATED", "LEAD", uuid);
    Map<String, Object> result = new LinkedHashMap<>(saved);
    result.put("created", true);
    return result;
  }

  /**
   * Accepts the voice agent's post-call record. Idempotent on the agent's own session identifier:
   * a record for a call this workspace already knows about updates that row rather than creating a
   * second one, so the agent's retry outbox can resend safely.
   */
  @Transactional
  public Map<String, Object> ingestCall(Long ws, Requests.CallIngest request, String key) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var lead = repo.get("leads", ws, request.leadId());
    if (request.projectId() != null) project(ws, request.projectId());
    if (key != null && (key.length() > 120 || !key.matches("[A-Za-z0-9_:.-]+")))
      throw ApiException.bad("Invalid Idempotency-Key");
    var prior =
        repo.sql()
            .query(
                "SELECT * FROM voice_sessions WHERE workspace_id=:ws AND (data->>'callId'=:call OR"
                    + " data->>'externalId'=:session OR data->>'voiceSessionId'=:session) ORDER BY"
                    + " id LIMIT 1",
                fields("ws", ws, "call", request.callId(), "session", request.voiceSessionId()),
                repo::row);
    Long uuid = prior.isEmpty() ? null : id(prior.getFirst().get("id"));
    if (uuid != null && !request.leadId().equals(id(prior.getFirst().get("leadId"))))
      throw ApiException.conflict("This call is already recorded against another lead");

    // A row already carrying this callId means the agent's outbox is resending a record we have.
    // The session row is refreshed, but the append-only detail tables must not gain a duplicate.
    boolean resend = !prior.isEmpty() && request.callId().equals(prior.getFirst().get("callId"));
    Map<String, Object> data = prior.isEmpty() ? fields() : new LinkedHashMap<>(prior.getFirst());
    data.putAll(mapper.map(request));
    data.put("externalId", request.voiceSessionId());
    data.put("leadName", lead.get("name"));
    String state = request.failureReason() == null ? "COMPLETED" : "FAILED";
    var saved =
        repo.save(
            "voice_sessions",
            ws,
            uuid,
            data,
            fields("lead_id", request.leadId(), "status", state));
    uuid = id(saved.get("id"));
    if (!resend) {
      saveCallDetails(ws, uuid, fields("status", state, "outcome", request.intent()));
      if (request.transcript() != null && !request.transcript().isEmpty())
        repo.event(
            "voice_transcripts", ws, "voice_session_id", uuid,
            fields("transcript", request.transcript()));
      if (request.summary() != null && !request.summary().isBlank())
        repo.event(
            "voice_summaries", ws, "voice_session_id", uuid, fields("summary", request.summary()));
      repo.event(
          "voice_session_requirements", ws, "voice_session_id", uuid,
          fields(
              "budget", request.budget(), "bhk", request.bhk(), "location", request.location(),
              "propertyType", request.propertyType(), "timeline", request.timeline(),
              "intent", request.intent(), "leadScore", request.leadScore()));
      updateLeadFromCall(ws, request, lead);
      activity(
          ws, request.leadId(), "CALL_COMPLETED",
          state.equals("FAILED") ? "Voice call ended without completing" : "Voice call recorded");
      event(ws, "CALL_RECORDED", "VOICE_SESSION", uuid);
    }
    return saved;
  }

  /**
   * Applies what the call learned to the lead. Status only ever moves forward from NEW/CONTACTED,
   * so a later call cannot reopen a lead an agent has already qualified or handed over.
   */
  private void updateLeadFromCall(Long ws, Requests.CallIngest request, Map<String, Object> lead) {
    Map<String, Object> patch = fields();
    if (request.customerName() != null && !request.customerName().isBlank())
      patch.put("customerName", request.customerName().trim());
    for (var entry :
        fields(
                "budgetMax", request.budget(), "location", request.location(),
                "propertyType", request.propertyType(), "timeline", request.timeline(),
                "leadScore", request.leadScore(), "lastCallSummary", request.summary())
            .entrySet())
      if (entry.getValue() != null) patch.put(entry.getKey(), entry.getValue());
    if (request.bhk() != null && !request.bhk().isEmpty()) patch.put("bhk", request.bhk());
    if (Boolean.TRUE.equals(request.doNotCall())) {
      patch.put("doNotCall", true);
      patch.put("doNotCallBasis", request.doNotCallBasis());
    }
    String current = String.valueOf(lead.get("status"));
    String next =
        Boolean.TRUE.equals(request.doNotCall())
            ? "NOT_INTERESTED"
            : Set.of("NEW", "CONTACTED").contains(current) ? "CONTACTED" : current;
    repo.sql()
        .update(
            "UPDATE leads SET status=:status,data=data||CAST(:patch AS jsonb),updated_at=now()"
                + " WHERE workspace_id=:ws AND id=:id",
            fields(
                "status", next, "patch", mapper.write(patch), "ws", ws, "id", request.leadId()));
    if (!next.equals(current))
      repo.event(
          "lead_status_history", ws, "lead_id", request.leadId(),
          fields("from", current, "to", next, "reason", "Voice call outcome"));
  }

  @Transactional(noRollbackFor = ExternalServiceException.class)
  public Map<String, Object> refreshCall(Long ws, Long uuid) {
    tenant.require(ws);
    var data = new LinkedHashMap<>(repo.get("voice_sessions", ws, uuid));
    var lead = repo.get("leads", ws, id(data.get("leadId")));
    Map<String, Object> payload =
        fields(
            "workspaceId",
            ws.toString(),
            "externalId",
            data.get("externalId"),
            "leadId",
            data.get("leadId"),
            "language",
            lead.get("language"));
    try {
      var result = voice.getCallDetails(payload);
      data.putAll(result);
      var saved =
          repo.save(
              "voice_sessions",
              ws,
              uuid,
              data,
              fields("status", result.getOrDefault("status", data.get("status"))));
      saveCallDetails(ws, uuid, data);
      event(ws, "CALL_REFRESHED", "VOICE_SESSION", uuid);
      return saved;
    } catch (ExternalServiceException e) {
      event(ws, "EXTERNAL_SERVICE_FAILED", "VOICE_SESSION", uuid);
      throw e;
    }
  }

  @Transactional
  public Map<String, Object> visit(Long ws, Long uuid, Requests.Visit request) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var lead = repo.get("leads", ws, request.leadId());
    var project = repo.get("projects", ws, request.projectId());
    tenant.member(ws, request.agentId());
    String state =
        status(
            request.status(),
            "CONFIRMED",
            "REQUESTED",
            "CONFIRMED",
            "RESCHEDULED",
            "CANCELLED",
            "COMPLETED",
            "NO_SHOW");
    Map<String, Object> old = uuid == null ? null : repo.get("appointments", ws, uuid);
    if (old != null
        && (!request.leadId().equals(id(old.get("leadId")))
            || !request.projectId().equals(id(old.get("projectId")))
            || !Objects.equals(request.unitId(), id(old.get("unitId"))))) {
      Long linked =
          repo.sql()
              .queryForObject(
                  "SELECT count(*) FROM handover_records WHERE workspace_id=:ws AND"
                      + " appointment_id=:id",
                  Map.of("ws", ws, "id", uuid),
                  Long.class);
      if (linked != null && linked > 0)
        throw ApiException.conflict(
            "This visit is linked to a handover; its lead, project and unit cannot change");
    }
    boolean active = Set.of("REQUESTED", "CONFIRMED", "RESCHEDULED").contains(state);
    if (active) {
      if (request.scheduledAt().isBefore(Instant.now().minusSeconds(60)))
        throw ApiException.bad("Site visits must be scheduled in the future");
      if (!project.get("status").equals("ACTIVE"))
        throw ApiException.conflict("Project is not active");
    }
    if (request.unitId() != null) {
      var unit = repo.get("units", ws, request.unitId());
      if (!request.projectId().equals(id(unit.get("projectId"))))
        throw ApiException.bad("Unit belongs to another project");
      if (active && !unit.get("status").equals("AVAILABLE"))
        throw ApiException.conflict("Unit is no longer available");
    }
    if (active) {
      Map<String, Object> params =
          fields(
              "ws",
              ws,
              "agent",
              request.agentId(),
              "lead",
              request.leadId(),
              "start",
              Timestamp.from(request.scheduledAt()),
              "end",
              Timestamp.from(request.scheduledAt().plusSeconds(request.durationMinutes() * 60L)),
              "id",
              uuid == null ? 0L : uuid);
      long count =
          Objects.requireNonNull(
              repo.sql()
                  .queryForObject(
                      "SELECT count(*) FROM appointments WHERE workspace_id=:ws AND id<>:id AND"
                          + " status IN ('REQUESTED','CONFIRMED','RESCHEDULED') AND"
                          + " (agent_id=:agent OR lead_id=:lead) AND scheduled_at<:end AND"
                          + " scheduled_at+duration_minutes*interval '1 minute'>:start",
                      params,
                      Long.class));
      if (count > 0)
        throw ApiException.conflict("This agent or lead already has an overlapping site visit");
    }
    Map<String, Object> data = mapper.map(request);
    data.put(
        "confirmationStatus",
        status(
            request.confirmationStatus(),
            old == null ? "PENDING" : string(old, "confirmationStatus", "PENDING"),
            "PENDING",
            "CONFIRMED",
            "DECLINED"));
    data.put("notificationStatus", "PENDING");
    data.put("leadName", lead.get("name"));
    data.put("projectName", project.get("name"));
    var saved =
        repo.save(
            "appointments",
            ws,
            uuid,
            data,
            fields(
                "project_id",
                request.projectId(),
                "lead_id",
                request.leadId(),
                "unit_id",
                request.unitId(),
                "agent_id",
                request.agentId(),
                "scheduled_at",
                Timestamp.from(request.scheduledAt()),
                "duration_minutes",
                request.durationMinutes(),
                "status",
                state));
    Long resource = id(saved.get("id"));
    repo.event(
        "appointment_status_history",
        ws,
        "appointment_id",
        resource,
        fields(
            "status",
            state,
            "previousStatus",
            old == null ? null : old.get("status"),
            "scheduledAt",
            request.scheduledAt()));
    repo.event(
        "appointment_participants",
        ws,
        "appointment_id",
        resource,
        fields("leadId", request.leadId(), "agentId", request.agentId()));
    String notice =
        notify(
            ws,
            request.agentId(),
            state.equals("CANCELLED")
                ? "SITE_VISIT_CANCELLED"
                : state.equals("RESCHEDULED")
                    ? "SITE_VISIT_RESCHEDULED"
                    : "SITE_VISIT_CONFIRMATION",
            "Site visit " + state.toLowerCase(Locale.ROOT) + " for " + lead.get("name"),
            resource);
    saved.put("notificationStatus", notice);
    repo.save("appointments", ws, resource, saved, Map.of());
    activity(
        ws,
        request.leadId(),
        "SITE_VISIT_" + state,
        "Site visit " + state.toLowerCase(Locale.ROOT));
    if (active || state.equals("COMPLETED")) {
      String leadState = state.equals("COMPLETED") ? "VISIT_COMPLETED" : "VISIT_PLANNED";
      repo.save("leads", ws, request.leadId(), lead, fields("status", leadState));
      repo.event(
          "lead_status_history",
          ws,
          "lead_id",
          request.leadId(),
          fields("status", leadState, "previousStatus", lead.get("status")));
    }
    scheduleReminder(
        ws,
        request.agentId(),
        "SITE_VISIT_REMINDER",
        resource,
        active ? request.scheduledAt().minusSeconds(86400) : null,
        "Upcoming site visit for " + lead.get("name"));
    event(ws, uuid == null ? "SITE_VISIT_CREATED" : "SITE_VISIT_UPDATED", "APPOINTMENT", resource);
    return saved;
  }

  @Transactional
  public Map<String, Object> handover(Long ws, Long uuid, Requests.Handover request) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var lead = repo.get("leads", ws, request.leadId());
    tenant.member(ws, request.agentId());
    if (uuid != null) repo.get("handover_records", ws, uuid);
    if (request.projectId() != null) project(ws, request.projectId());
    if (request.unitId() != null) {
      if (request.projectId() == null) throw ApiException.bad("Project is required with a unit");
      var unit = repo.get("units", ws, request.unitId());
      if (!request.projectId().equals(id(unit.get("projectId"))))
        throw ApiException.bad("Unit belongs to another project");
    }
    if (request.appointmentId() != null) {
      var appointment = repo.get("appointments", ws, request.appointmentId());
      if (!request.leadId().equals(id(appointment.get("leadId")))
          || request.projectId() == null
          || !request.projectId().equals(id(appointment.get("projectId"))))
        throw ApiException.bad("Visit must belong to this lead and project");
    }
    String state =
        status(request.status(), "ASSIGNED", "PENDING", "ASSIGNED", "ACCEPTED", "COMPLETED");
    Map<String, Object> data = mapper.map(request);
    data.put("handoverAt", Instant.now().toString());
    data.put("leadName", lead.get("name"));
    data.put(
        "scopeNotice",
        "The human real-estate agent handles all later buying and legal activities.");
    var saved =
        repo.save(
            "handover_records",
            ws,
            uuid,
            data,
            fields(
                "lead_id",
                request.leadId(),
                "agent_id",
                request.agentId(),
                "project_id",
                request.projectId(),
                "unit_id",
                request.unitId(),
                "appointment_id",
                request.appointmentId(),
                "status",
                state));
    Long resource = id(saved.get("id"));
    repo.save(
        "leads",
        ws,
        request.leadId(),
        lead,
        fields("status", "HANDED_OVER", "assigned_agent_id", request.agentId()));
    repo.event(
        "lead_status_history",
        ws,
        "lead_id",
        request.leadId(),
        fields("status", "HANDED_OVER", "previousStatus", lead.get("status")));
    activity(ws, request.leadId(), "HANDED_OVER", "Handover " + state.toLowerCase(Locale.ROOT));
    notify(ws, request.agentId(), "HANDOVER", "A customer handover is ready for review", resource);
    event(ws, "AGENT_HANDOVER", "HANDOVER", resource);
    return get("handover_records", ws, resource);
  }

  private String notify(Long ws, Long user, String type, String message, Long resource) {
    Map<String, Object> data =
        fields(
            "type",
            type,
            "title",
            type.replace('_', ' '),
            "message",
            message,
            "resourceId",
            resource,
            "read",
            false);
    var saved =
        repo.save("notifications", ws, null, data, fields("user_id", user, "status", "PENDING"));
    Long uuid = id(saved.get("id"));
    Map<String, Object> payload =
        fields(
            "workspaceId",
            ws.toString(),
            "notificationId",
            uuid.toString(),
            "recipientUserId",
            user == null ? null : user.toString(),
            "type",
            type,
            "message",
            message);
    String state;
    Map<String, Object> delivery;
    try {
      delivery = notification.send(payload);
      state = delivery.getOrDefault("status", "PENDING").toString();
    } catch (ExternalServiceException e) {
      state = "FAILED";
      delivery = fields("status", state, "error", e.getMessage());
      event(ws, "EXTERNAL_SERVICE_FAILED", "NOTIFICATION", uuid);
    }
    data.put("mock", delivery.getOrDefault("mock", false));
    repo.save("notifications", ws, uuid, data, fields("status", state));
    repo.event("notification_deliveries", ws, "notification_id", uuid, delivery);
    repo.save(
        "outbox_events",
        ws,
        null,
        fields("type", type, "notificationId", uuid, "status", state),
        Map.of());
    return state;
  }

  @Transactional
  public Map<String, Object> readNotification(Long ws, Long uuid) {
    tenant.require(ws);
    var data = new LinkedHashMap<>(repo.get("notifications", ws, uuid));
    if (data.get("userId") != null && !tenant.user().equals(id(data.get("userId"))))
      throw ApiException.forbidden();
    data.put("read", true);
    return repo.save("notifications", ws, uuid, data, Map.of());
  }

  public Map<String, Object> dashboard(Long ws) {
    tenant.require(ws);
    Map<String, Object> metrics = new LinkedHashMap<>();
    metrics.put("totalLeads", count(ws, "leads", null));
    metrics.put("newLeads", count(ws, "leads", "NEW"));
    metrics.put("qualifiedLeads", count(ws, "leads", "QUALIFIED"));
    metrics.put("totalProjects", count(ws, "projects", null));
    metrics.put("availableUnits", count(ws, "units", "AVAILABLE"));
    metrics.put("siteVisitsBooked", count(ws, "appointments", null));
    metrics.put("callsHandled", count(ws, "voice_sessions", null));
    var upcoming =
        repo.sql()
            .query(
                "SELECT * FROM appointments WHERE workspace_id=:ws AND scheduled_at>=now() AND"
                    + " status IN ('REQUESTED','CONFIRMED','RESCHEDULED') ORDER BY scheduled_at"
                    + " LIMIT 8",
                Map.of("ws", ws),
                repo::row);
    var followUps =
        repo.sql()
            .query(
                "SELECT * FROM leads WHERE workspace_id=:ws AND data->>'followUpAt' IS NOT NULL AND"
                    + " (data->>'followUpAt')::timestamptz>=now() ORDER BY"
                    + " (data->>'followUpAt')::timestamptz LIMIT 8",
                Map.of("ws", ws),
                repo::row);
    var conversion =
        repo.sql()
            .queryForList(
                "SELECT status,count(*) AS count FROM leads WHERE workspace_id=:ws GROUP BY status"
                    + " ORDER BY status",
                Map.of("ws", ws));
    boolean demo =
        Boolean.TRUE.equals(
            repo.sql()
                .queryForObject(
                    "SELECT demo FROM workspaces WHERE id=:ws", Map.of("ws", ws), Boolean.class));
    return fields(
        "metrics",
        metrics,
        "upcomingVisits",
        upcoming,
        "recentActivities",
        repo.list("audit_logs", ws, Map.of("size", "8")).items().stream()
            .map(
                a ->
                    fields(
                        "id",
                        a.get("id"),
                        "description",
                        a.get("description"),
                        "createdAt",
                        a.get("createdAt")))
            .toList(),
        "followUps",
        followUps,
        "conversionSummary",
        conversion,
        "demo",
        demo);
  }

  private void scheduleReminder(
      Long ws, Long recipient, String type, Long resource, Instant due, String message) {
    repo.sql()
        .update(
            "UPDATE notifications SET status='CANCELLED',updated_at=now() WHERE workspace_id=:ws"
                + " AND status='SCHEDULED' AND data->>'type'=:type AND"
                + " data->>'resourceId'=:resource",
            Map.of("ws", ws, "type", type, "resource", resource.toString()));
    if (due != null)
      repo.save(
          "notifications",
          ws,
          null,
          fields(
              "type",
              type,
              "title",
              type.replace('_', ' '),
              "message",
              message,
              "resourceId",
              resource.toString(),
              "dueAt",
              due.isBefore(Instant.now()) ? Instant.now().toString() : due.toString(),
              "read",
              false),
          fields("user_id", recipient, "status", "SCHEDULED"));
  }

  private long count(Long ws, String table, String state) {
    return Objects.requireNonNull(
        repo.sql()
            .queryForObject(
                "SELECT count(*) FROM "
                    + table
                    + " WHERE workspace_id=:ws"
                    + (state == null ? "" : " AND status=:status"),
                state == null ? Map.of("ws", ws) : Map.of("ws", ws, "status", state),
                Long.class));
  }
}
