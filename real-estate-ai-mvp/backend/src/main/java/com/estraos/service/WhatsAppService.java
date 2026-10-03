package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.calls.CallingHours;
import com.estraos.integration.ExternalServiceException;
import com.estraos.integration.WhatsAppClient;
import com.estraos.mapper.DtoMapper;
import com.estraos.repository.TenantRepository;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * Customer WhatsApp messages through approved templates (see docs/whatsapp-templates.md).
 *
 * <p>Nothing is sent unless the customer said yes on a call: the consent and its timestamp are on
 * the lead ({@code whatsappConsent}, {@code whatsappConsentAt}). Every send — delivered, mocked or
 * failed — is a notification with channel WHATSAPP plus a delivery row holding the provider's
 * message id, which the status webhook later updates. Failures are recorded, never thrown.
 */
@Service
public class WhatsAppService {
  private static final Logger log = LoggerFactory.getLogger(WhatsAppService.class);
  private static final DateTimeFormatter WHEN =
      DateTimeFormatter.ofPattern("EEEE, d MMM yyyy 'at' h:mm a", Locale.ENGLISH);

  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final WhatsAppClient client;
  private final AuditService audit;
  private final DtoMapper mapper;
  private final Map<String, String> languages;
  private final String officePhone;

  public WhatsAppService(
      NamedParameterJdbcTemplate db, TenantRepository repo, WhatsAppClient client, AuditService audit,
      DtoMapper mapper,
      @Value("${app.whatsapp.template-lang-map:{\"en\":\"en\",\"hi\":\"hi\",\"mr\":\"mr\",\"gu\":\"gu\"}}")
          String languageMap,
      @Value("${app.whatsapp.office-phone:}") String officePhone) {
    this.db = db;
    this.repo = repo;
    this.client = client;
    this.audit = audit;
    this.mapper = mapper;
    Map<String, String> parsed = new HashMap<>();
    mapper.read(languageMap).forEach((key, value) -> parsed.put(key, String.valueOf(value)));
    this.languages = parsed;
    this.officePhone = officePhone;
  }

  public record Result(boolean sent, String reason, Long notificationId) {}

  static boolean consented(Map<String, Object> lead) {
    return Boolean.TRUE.equals(lead.get("whatsappConsent")) && !Boolean.TRUE.equals(lead.get("doNotCall"));
  }

  private static Map<String, Object> text(String value) {
    // The Cloud API rejects empty parameters.
    return Map.of("type", "text", "text", value == null || value.isBlank() ? "-" : value);
  }

  private static List<Map<String, Object>> body(String... values) {
    return List.of(Map.of("type", "body", "parameters", Arrays.stream(values).map(WhatsAppService::text).toList()));
  }

  private boolean alreadySent(Long ws, String type, Long resource, String marker) {
    Integer n = db.queryForObject(
        "SELECT count(*) FROM notifications WHERE workspace_id=:ws AND data->>'type'=:type AND"
            + " data->>'resourceId'=:resource AND data->>'marker'=:marker AND status NOT IN ('FAILED')",
        Map.of("ws", ws, "type", type, "resource", resource.toString(), "marker", marker), Integer.class);
    return n != null && n > 0;
  }

  private Result send(Long ws, Map<String, Object> lead, String type, String template, Long resource,
                      String marker, List<Map<String, Object>> components) {
    return deliver(ws, lead, type, template, resource, marker, () -> client.sendTemplate(EstateService.fields(
        "workspaceId", ws.toString(), "to", String.valueOf(lead.get("phone")), "template", template,
        "templateLanguage", language(lead), "components", components)));
  }

  private String language(Map<String, Object> lead) {
    return languages.getOrDefault(String.valueOf(lead.getOrDefault("language", "en")), "en");
  }

  /** Records the notification, runs the send, and stores the outcome either way. */
  private Result deliver(Long ws, Map<String, Object> lead, String type, String template, Long resource,
                         String marker, java.util.function.Supplier<Map<String, Object>> sendNow) {
    if (!consented(lead)) return new Result(false, "NO_CONSENT", null);
    if (alreadySent(ws, type, resource, marker)) return new Result(false, "ALREADY_SENT", null);
    String tail = DncService.tail(String.valueOf(lead.get("phone")));
    Map<String, Object> data = EstateService.fields(
        "type", type, "title", type.replace('_', ' '), "channel", "WHATSAPP", "template", template,
        "templateLanguage", language(lead), "resourceId", resource.toString(), "leadId", lead.get("id"),
        "marker", marker, "recipient", "…" + tail.substring(Math.max(0, tail.length() - 4)),
        "message", "WhatsApp " + template + " to " + lead.get("name"), "read", false);
    var saved = repo.save("notifications", ws, null, data, EstateService.fields("user_id", null, "status", "PENDING"));
    Long id = EstateService.id(saved.get("id"));
    Map<String, Object> delivery;
    String status;
    try {
      delivery = new LinkedHashMap<>(sendNow.get());
      status = String.valueOf(delivery.getOrDefault("status", "SENT"));
      data.put("providerMessageId", delivery.get("messageId"));
      data.put("mock", delivery.getOrDefault("mock", false));
    } catch (ExternalServiceException | IllegalArgumentException e) {
      status = "FAILED";
      delivery = EstateService.fields("status", status, "error", e.getMessage());
      audit.record(ws, null, "EXTERNAL_SERVICE_FAILED", "NOTIFICATION", id);
    }
    delivery.put("channel", "WHATSAPP");
    if (data.get("providerMessageId") != null) delivery.put("providerMessageId", data.get("providerMessageId"));
    repo.save("notifications", ws, id, data, Map.of("status", status));
    repo.event("notification_deliveries", ws, "notification_id", id, delivery);
    repo.event("lead_activities", ws, "lead_id", EstateService.id(lead.get("id")), EstateService.fields(
        "action", "WHATSAPP_" + (status.equals("FAILED") ? "FAILED" : "SENT"),
        "description", "WhatsApp " + template + (status.equals("FAILED") ? " could not be sent" : " sent")));
    return new Result(!status.equals("FAILED"), status, id);
  }

  private Map<String, Object> agent(Long agentId) {
    var rows = db.queryForList("SELECT name, phone FROM users WHERE id=:id", Map.of("id", agentId));
    return rows.isEmpty() ? Map.of() : rows.getFirst();
  }

  private static String mapLink(Map<String, Object> project) {
    Object custom = project.get("mapUrl");
    if (custom != null && custom.toString().startsWith("https://")) return custom.toString();
    String query = project.get("name") + ", " + Objects.requireNonNullElse(project.get("location"), "");
    return "https://www.google.com/maps/search/?api=1&query=" + URLEncoder.encode(query, StandardCharsets.UTF_8);
  }

  private Result visitMessage(Long ws, Long appointmentId, String type, String template) {
    try {
      var visit = repo.get("appointments", ws, appointmentId);
      var lead = repo.get("leads", ws, EstateService.id(visit.get("leadId")));
      var project = repo.get("projects", ws, EstateService.id(visit.get("projectId")));
      var agent = agent(EstateService.id(visit.get("agentId")));
      Instant at = Instant.parse(visit.get("scheduledAt").toString());
      String when = WHEN.format(at.atZone(CallingHours.IST)) + " IST";
      String phone = Objects.toString(agent.get("phone"), officePhone);
      List<Map<String, Object>> components = type.equals("WHATSAPP_VISIT_CONFIRMATION")
          ? body(String.valueOf(lead.get("name")), String.valueOf(project.get("name")), when,
              Objects.toString(project.get("location"), ""), mapLink(project),
              Objects.toString(agent.get("name"), ""), phone)
          : body(String.valueOf(lead.get("name")), String.valueOf(project.get("name")), when,
              Objects.toString(project.get("location"), ""), Objects.toString(agent.get("name"), ""), phone);
      return send(ws, lead, type, template, appointmentId, at.toString(), components);
    } catch (RuntimeException e) {
      log.warn("WhatsApp {} for visit {} not sent: {}", template, appointmentId, e.getMessage());
      return new Result(false, "ERROR", null);
    }
  }

  public Result visitConfirmation(Long ws, Long appointmentId) {
    return visitMessage(ws, appointmentId, "WHATSAPP_VISIT_CONFIRMATION", "visit_confirmation");
  }

  public Result visitReminder(Long ws, Long appointmentId) {
    return visitMessage(ws, appointmentId, "WHATSAPP_VISIT_REMINDER", "visit_reminder");
  }

  /** The project's published brochure PDF as a document header. */
  public Result brochure(Long ws, Long leadId, Long projectId) {
    try {
      var lead = repo.get("leads", ws, leadId);
      if (!consented(lead)) return new Result(false, "NO_CONSENT", null);
      var project = repo.get("projects", ws, projectId);
      var files = db.queryForList(
          "SELECT f.filename, f.content_type, f.content, d.id AS document_id FROM document_files f JOIN"
              + " property_documents d ON d.workspace_id=f.workspace_id AND d.id=f.document_id WHERE"
              + " f.workspace_id=:ws AND d.project_id=:project AND d.status='PUBLISHED' AND"
              + " f.content_type='application/pdf' ORDER BY (d.data->>'docType'='BROCHURE') DESC,"
              + " (lower(d.title) LIKE '%brochure%') DESC, d.updated_at DESC LIMIT 1",
          Map.of("ws", ws, "project", projectId));
      if (files.isEmpty()) return new Result(false, "NO_BROCHURE", null);
      var file = files.getFirst();
      String marker = "doc-" + file.get("document_id") + "-lead-" + leadId;
      return deliver(ws, lead, "WHATSAPP_BROCHURE", "brochure_share", projectId, marker, () -> {
        String media = client.uploadMedia((String) file.get("filename"), (String) file.get("content_type"),
            (byte[]) file.get("content"));
        List<Map<String, Object>> components = new ArrayList<>();
        components.add(Map.of("type", "header", "parameters", List.of(Map.of("type", "document",
            "document", Map.of("id", media, "filename", file.get("filename"))))));
        components.addAll(body(String.valueOf(lead.get("name")), String.valueOf(project.get("name"))));
        return client.sendTemplate(EstateService.fields("workspaceId", ws.toString(), "to",
            String.valueOf(lead.get("phone")), "template", "brochure_share", "templateLanguage", language(lead),
            "components", components));
      });
    } catch (RuntimeException e) {
      log.warn("WhatsApp brochure for lead {} not sent: {}", leadId, e.getMessage());
      return new Result(false, "ERROR", null);
    }
  }

  // ---------------------------------------------------------------- delivery-status webhook

  private static final Map<String, String> STATUS =
      Map.of("sent", "SENT", "delivered", "DELIVERED", "read", "READ", "failed", "FAILED");

  /** Applies a Cloud API status webhook. Returns how many messages it updated. */
  @SuppressWarnings("unchecked")
  public int onStatusWebhook(Map<String, Object> payload) {
    int updated = 0;
    for (Object entry : (List<Object>) payload.getOrDefault("entry", List.of())) {
      for (Object change : (List<Object>) ((Map<String, Object>) entry).getOrDefault("changes", List.of())) {
        Map<String, Object> value = (Map<String, Object>) ((Map<String, Object>) change).getOrDefault("value", Map.of());
        for (Object raw : (List<Object>) value.getOrDefault("statuses", List.of())) {
          Map<String, Object> status = (Map<String, Object>) raw;
          String id = String.valueOf(status.get("id"));
          String state = STATUS.getOrDefault(String.valueOf(status.get("status")), "UNKNOWN");
          var rows = db.queryForList(
              "SELECT workspace_id, id FROM notifications WHERE data->>'providerMessageId'=:id LIMIT 1",
              Map.of("id", id));
          if (rows.isEmpty()) continue;
          Long ws = ((Number) rows.getFirst().get("workspace_id")).longValue();
          Long notification = ((Number) rows.getFirst().get("id")).longValue();
          db.update("UPDATE notifications SET status=:status, updated_at=now() WHERE workspace_id=:ws AND id=:id",
              Map.of("status", state, "ws", ws, "id", notification));
          repo.event("notification_deliveries", ws, "notification_id", notification, EstateService.fields(
              "channel", "WHATSAPP", "providerMessageId", id, "status", state,
              "providerTimestamp", status.get("timestamp"), "errors", status.get("errors")));
          updated++;
        }
      }
    }
    return updated;
  }
}
