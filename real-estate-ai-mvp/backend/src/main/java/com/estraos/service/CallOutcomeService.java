package com.estraos.service;

import com.estraos.calls.CallScheduleService;
import com.estraos.dto.Requests;
import com.estraos.exception.ApiException;
import com.estraos.repository.TenantRepository;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * What a finished call means for the CRM, beyond the call record itself: a handover for a hot or
 * escalated lead, a callback the customer asked for, the outcome of a reminder call for a visit,
 * the customer's WhatsApp consent and the messages they asked for. Runs once per call, inside the
 * ingest transaction (a resent record does not repeat it).
 */
@Service
public class CallOutcomeService {
  private static final Logger log = LoggerFactory.getLogger(CallOutcomeService.class);
  private final TenantRepository repo;
  private final NamedParameterJdbcTemplate db;
  private final AgentAssignment agents;
  private final CallScheduleService schedule;
  private final WhatsAppService whatsapp;
  private final Notifier notifier;

  public CallOutcomeService(TenantRepository repo, NamedParameterJdbcTemplate db, AgentAssignment agents,
                            CallScheduleService schedule, WhatsAppService whatsapp, Notifier notifier) {
    this.repo = repo;
    this.db = db;
    this.agents = agents;
    this.schedule = schedule;
    this.whatsapp = whatsapp;
    this.notifier = notifier;
  }

  private void activity(Long ws, Long lead, String action, String description, Long actor) {
    repo.event("lead_activities", ws, "lead_id", lead,
        EstateService.fields("action", action, "description", description, "userId", actor));
  }

  public Map<String, Object> apply(Long ws, Requests.CallIngest call, Long sessionId, Long actor) {
    Map<String, Object> applied = new LinkedHashMap<>();
    var lead = repo.get("leads", ws, call.leadId());
    if (call.visitOutcome() != null && call.appointmentId() != null)
      applied.put("visitOutcome", visitOutcome(ws, call, actor));
    if (call.callbackAt() != null) applied.put("callbackId", callback(ws, call, actor));
    boolean hot = "HOT".equals(call.leadTemperature());
    if (Boolean.TRUE.equals(call.handoverRequested()) || hot)
      applied.put("handoverId", handover(ws, call, lead, sessionId, hot, actor));
    // A scheduled call this record answers is done; so is the callback it was placed for.
    db.update("UPDATE scheduled_calls SET status='DONE', updated_at=now(), data=data||jsonb_build_object("
            + "'completedBySession', CAST(:session AS text)) WHERE workspace_id=:ws AND lead_id=:lead AND"
            + " status='DIALING' AND (data->>'externalId'=:external OR idempotency_key=:external)",
        Map.of("ws", ws, "lead", call.leadId(), "session", sessionId.toString(), "external", call.voiceSessionId()));
    if (call.callbackId() != null)
      db.update("UPDATE callbacks SET status='DONE', updated_at=now() WHERE workspace_id=:ws AND id=:id AND"
          + " status IN ('SCHEDULED','DIALING')", Map.of("ws", ws, "id", call.callbackId()));
    if (Boolean.TRUE.equals(call.whatsappConsent())) applied.put("whatsapp", whatsapp(ws, call, actor));
    return applied;
  }

  private String visitOutcome(Long ws, Requests.CallIngest call, Long actor) {
    var visit = new LinkedHashMap<>(repo.get("appointments", ws, call.appointmentId()));
    if (!call.leadId().equals(EstateService.id(visit.get("leadId"))))
      throw ApiException.bad("The visit belongs to another lead");
    String status = String.valueOf(visit.get("status"));
    visit.put("lastCallOutcome", call.visitOutcome());
    visit.put("lastCallId", call.callId());
    switch (call.visitOutcome()) {
      case "CONFIRMED" -> {
        visit.put("confirmationStatus", "CONFIRMED");
        if (Set.of("REQUESTED", "RESCHEDULED").contains(status)) status = "CONFIRMED";
      }
      case "CANCELLED" -> {
        if (!Set.of("CANCELLED", "COMPLETED", "NO_SHOW").contains(status)) status = "CANCELLED";
        visit.put("confirmationStatus", "DECLINED");
      }
      default -> { /* RESCHEDULED was applied by the reschedule call itself; NO_ANSWER changes nothing */ }
    }
    if (!status.equals(visit.get("status")))
      repo.event("appointment_status_history", ws, "appointment_id", call.appointmentId(),
          EstateService.fields("status", status, "previousStatus", visit.get("status"), "source", "VOICE_AGENT"));
    repo.save("appointments", ws, call.appointmentId(), visit, EstateService.fields("status", status));
    if (status.equals("CANCELLED")) schedule.visitReminders(ws, call.appointmentId());
    activity(ws, call.leadId(), "VISIT_" + call.visitOutcome(),
        "Reminder call: visit " + call.visitOutcome().toLowerCase(Locale.ROOT).replace('_', ' '), actor);
    return call.visitOutcome();
  }

  private String callback(Long ws, Requests.CallIngest call, Long actor) {
    Instant due = call.callbackAt();
    var existing = db.queryForList(
        "SELECT id FROM callbacks WHERE workspace_id=:ws AND lead_id=:lead AND data->>'callId'=:call",
        Map.of("ws", ws, "lead", call.leadId(), "call", call.callId()), Long.class);
    if (!existing.isEmpty()) return existing.getFirst().toString();
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("lead", call.leadId());
    params.put("due", Timestamp.from(due));
    params.put("reason", "Customer asked to be called back");
    params.put("call", call.callId());
    Long id = db.queryForObject(
        "INSERT INTO callbacks(workspace_id,lead_id,due_at,reason,requested_by,data) VALUES"
            + " (:ws,:lead,:due,:reason,'CUSTOMER',jsonb_build_object('callId', CAST(:call AS text),"
            + " 'source', 'VOICE_AGENT')) RETURNING id", params, Long.class);
    schedule.callback(ws, id, call.leadId(), due);
    activity(ws, call.leadId(), "CALLBACK_SCHEDULED", "Callback requested for " + due, actor);
    return id.toString();
  }

  private String handover(Long ws, Requests.CallIngest call, Map<String, Object> lead, Long sessionId,
                          boolean hot, Long actor) {
    var open = db.queryForList(
        "SELECT id FROM handover_records WHERE workspace_id=:ws AND lead_id=:lead AND status IN"
            + " ('PENDING','ASSIGNED') ORDER BY id DESC LIMIT 1",
        Map.of("ws", ws, "lead", call.leadId()), Long.class);
    String reason = call.handoverReason() != null ? call.handoverReason() : hot ? "HOT_LEAD" : "CUSTOMER_ASKED";
    List<String> questions = Objects.requireNonNullElse(call.unansweredQuestions(), List.of());
    if (!open.isEmpty()) {
      // One open handover per lead: add this call's context to it rather than opening another.
      var record = new LinkedHashMap<>(repo.get("handover_records", ws, open.getFirst()));
      String previous = Objects.toString(record.get("questions"), "");
      String added = String.join("\n", questions);
      record.put("questions", (previous + (previous.isBlank() || added.isBlank() ? "" : "\n") + added).strip());
      record.put("lastCallId", call.callId());
      repo.save("handover_records", ws, open.getFirst(), record, Map.of());
      return open.getFirst().toString();
    }
    Long preferred = EstateService.id(lead.get("assignedAgentId"));
    Long project = call.projectId();
    AgentAssignment.Choice agent;
    try {
      agent = agents.forHandover(ws, project, preferred);
    } catch (ApiException e) {
      log.warn("Handover for lead {} not created: {}", call.leadId(), e.getMessage());
      notifier.managers(ws, "HANDOVER_UNASSIGNED",
          "A " + reason.toLowerCase(Locale.ROOT).replace('_', ' ') + " handover for " + lead.get("name")
              + " needs an agent", call.leadId());
      return null;
    }
    Map<String, Object> data = EstateService.fields(
        "notes", Objects.toString(call.summary(), ""), "questions", String.join("\n", questions),
        "reason", reason, "leadTemperature", call.leadTemperature(), "leadScore", call.leadScore(),
        "source", "VOICE_AGENT", "callId", call.callId(), "voiceSessionId", sessionId.toString(),
        "handoverAt", Instant.now().toString(), "leadName", lead.get("name"),
        "scopeNotice", "The human real-estate agent handles all later buying and legal activities.");
    var saved = repo.save("handover_records", ws, null, data, EstateService.fields(
        "lead_id", call.leadId(), "agent_id", agent.userId(), "project_id", project,
        "appointment_id", call.appointmentId(), "status", "PENDING"));
    Long id = EstateService.id(saved.get("id"));
    if (lead.get("assignedAgentId") == null)
      db.update("UPDATE leads SET assigned_agent_id=:agent, updated_at=now() WHERE workspace_id=:ws AND id=:id",
          Map.of("agent", agent.userId(), "ws", ws, "id", call.leadId()));
    notifier.notify(ws, agent.userId(), "HANDOVER",
        (hot ? "Hot lead: " : "Customer handover: ") + lead.get("name") + " ("
            + reason.toLowerCase(Locale.ROOT).replace('_', ' ') + ")", id);
    activity(ws, call.leadId(), "HANDOVER_REQUESTED",
        "Handover to " + agent.name() + " (" + reason.toLowerCase(Locale.ROOT).replace('_', ' ') + ")", actor);
    return id.toString();
  }

  private Map<String, Object> whatsapp(Long ws, Requests.CallIngest call, Long actor) {
    Map<String, Object> sent = new LinkedHashMap<>();
    List<String> requests = Objects.requireNonNullElse(call.whatsappRequests(), List.of());
    if (requests.contains("BROCHURE") && call.projectId() != null)
      sent.put("BROCHURE", whatsapp.brochure(ws, call.leadId(), call.projectId()).reason());
    Long visit = call.appointmentId();
    if (visit == null && requests.contains("VISIT_CONFIRMATION")) {
      var booked = db.queryForList(
          "SELECT id FROM appointments WHERE workspace_id=:ws AND lead_id=:lead AND data->>'callId'=:call"
              + " ORDER BY id DESC LIMIT 1", Map.of("ws", ws, "lead", call.leadId(), "call", call.callId()), Long.class);
      visit = booked.isEmpty() ? null : booked.getFirst();
    }
    if (visit != null && (requests.contains("VISIT_CONFIRMATION") || "RESCHEDULED".equals(call.visitOutcome())))
      sent.put("VISIT_CONFIRMATION", whatsapp.visitConfirmation(ws, visit).reason());
    return sent;
  }
}
