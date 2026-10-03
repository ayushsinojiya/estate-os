package com.estraos.calls;

import com.estraos.mapper.DtoMapper;
import com.estraos.repository.TenantRepository;
import java.sql.Timestamp;
import java.time.*;
import java.time.format.TextStyle;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * Decides which outbound calls exist and when they are due; {@link OutboundCallScheduler} places
 * them. Every row has a stable idempotency key that names its purpose (the visit, the time it was
 * booked for, the reminder kind), so the same reminder can never be scheduled twice and a
 * rescheduled visit gets fresh reminders while the old ones are cancelled.
 */
@Service
public class CallScheduleService {
  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final DtoMapper mapper;
  private final LocalTime dayBeforeAt;
  private final long sameDayHoursBefore;
  private final long newLeadDelaySeconds;

  public CallScheduleService(
      NamedParameterJdbcTemplate db,
      TenantRepository repo,
      DtoMapper mapper,
      @Value("${app.calls.visit-reminder-time:18:00}") String dayBeforeAt,
      @Value("${app.calls.same-day-hours-before:2}") long sameDayHoursBefore,
      @Value("${app.calls.new-lead-delay-s:120}") long newLeadDelaySeconds) {
    this.db = db;
    this.repo = repo;
    this.mapper = mapper;
    this.dayBeforeAt = LocalTime.parse(dayBeforeAt);
    this.sameDayHoursBefore = sameDayHoursBefore;
    this.newLeadDelaySeconds = newLeadDelaySeconds;
  }

  private boolean insert(Long ws, Long lead, String type, Instant due, String key, Long appointment,
                         Long callback, Map<String, Object> data) {
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("lead", lead);
    params.put("type", type);
    params.put("due", Timestamp.from(due));
    params.put("key", key);
    params.put("appointment", appointment);
    params.put("callback", callback);
    params.put("data", mapper.write(data));
    return db.update(
            "INSERT INTO scheduled_calls(workspace_id,lead_id,call_type,due_at,idempotency_key,"
                + "appointment_id,callback_id,data) VALUES (:ws,:lead,:type,:due,:key,:appointment,"
                + ":callback,CAST(:data AS jsonb)) ON CONFLICT (idempotency_key) DO NOTHING",
            params)
        == 1;
  }

  private void cancel(String where, Map<String, Object> params, String reason) {
    Map<String, Object> p = new HashMap<>(params);
    p.put("reason", reason);
    db.update(
        "UPDATE scheduled_calls SET status='CANCELLED', updated_at=now(), data=data||"
            + "jsonb_build_object('cancelReason', CAST(:reason AS text)) WHERE status='SCHEDULED' AND "
            + where,
        p);
  }

  /**
   * Day-before (at 18:00 IST by default) and same-day (two hours before) reminder calls for an
   * active visit. Reminders already due are not created: a visit booked for tomorrow morning at
   * 19:00 today gets only its same-day reminder.
   */
  public void visitReminders(Long ws, Long appointmentId) {
    var appointment = repo.get("appointments", ws, appointmentId);
    cancel("workspace_id=:ws AND appointment_id=:id AND call_type='VISIT_REMINDER'",
        Map.of("ws", ws, "id", appointmentId), "VISIT_CHANGED");
    if (!Set.of("REQUESTED", "CONFIRMED", "RESCHEDULED").contains(appointment.get("status"))) return;
    Instant at = Instant.parse(appointment.get("scheduledAt").toString());
    Long lead = Long.valueOf(appointment.get("leadId").toString());
    Instant now = Instant.now();
    Instant dayBefore = at.atZone(CallingHours.IST).toLocalDate().minusDays(1).atTime(dayBeforeAt)
        .atZone(CallingHours.IST).toInstant();
    if (dayBefore.isAfter(now))
      insert(ws, lead, "VISIT_REMINDER", dayBefore,
          "visit-" + appointmentId + "-day-before-" + at.getEpochSecond(), appointmentId, null,
          Map.of("reminder", "DAY_BEFORE", "visitAt", at.toString()));
    Instant sameDay = at.minus(Duration.ofHours(sameDayHoursBefore));
    if (sameDay.isAfter(now))
      insert(ws, lead, "VISIT_REMINDER", sameDay,
          "visit-" + appointmentId + "-same-day-" + at.getEpochSecond(), appointmentId, null,
          Map.of("reminder", "SAME_DAY", "visitAt", at.toString()));
  }

  public void callback(Long ws, Long callbackId, Long lead, Instant due) {
    cancel("workspace_id=:ws AND callback_id=:id", Map.of("ws", ws, "id", callbackId), "CALLBACK_CHANGED");
    insert(ws, lead, "CALLBACK", due, "callback-" + callbackId + "-" + due.getEpochSecond(), null,
        callbackId, Map.of());
  }

  public void cancelCallback(Long ws, Long callbackId) {
    cancel("workspace_id=:ws AND callback_id=:id", Map.of("ws", ws, "id", callbackId), "CALLBACK_CANCELLED");
  }

  /** First contact with a lead that arrived from the web or a portal. */
  public void newLead(Long ws, Long lead) {
    insert(ws, lead, "OUTBOUND_NEW_LEAD", Instant.now().plusSeconds(newLeadDelaySeconds),
        "new-lead-" + lead, null, null, Map.of());
  }

  public boolean reengagement(Long ws, Long lead, int attempt) {
    return insert(ws, lead, "RE_ENGAGEMENT", Instant.now(), "reengage-" + lead + "-" + attempt, null,
        null, Map.of("attempt", attempt));
  }

  // ---------------------------------------------------------------- what the agent is told

  /** "Saturday 11 AM", "Saturday 11:30 AM": how a time is said on the phone. */
  public static String spokenTime(Instant at) {
    ZonedDateTime local = at.atZone(CallingHours.IST);
    int hour = local.getHour() % 12 == 0 ? 12 : local.getHour() % 12;
    String minutes = local.getMinute() == 0 ? "" : String.format(":%02d", local.getMinute());
    return local.getDayOfWeek().getDisplayName(TextStyle.FULL, Locale.ENGLISH) + " " + hour + minutes
        + (local.getHour() < 12 ? " AM" : " PM");
  }

  /**
   * The context object sent with an outbound call: who the lead is, what is already known about
   * them, what was said last time, and — for a reminder — the visit. The agent opens differently
   * per call type using it, and never asks again for what is here.
   */
  public Map<String, Object> context(Long ws, Map<String, Object> lead, Long appointmentId, Long callbackId) {
    Map<String, Object> context = new LinkedHashMap<>();
    context.put("leadName", lead.get("name"));
    context.put("source", lead.get("source"));
    Map<String, Object> preferences = new LinkedHashMap<>();
    for (String key : List.of("intent", "budgetMin", "budgetMax", "location", "propertyType", "bhk",
        "possessionTimeline", "possessionPreference", "purpose"))
      if (lead.get(key) != null && !lead.get(key).toString().isBlank()) preferences.put(key, lead.get(key));
    context.put("knownPreferences", preferences);
    Object summary = lead.get("lastCallSummary");
    context.put("lastSummary", summary);
    Object projectId = lead.get("projectId");
    if (projectId != null) {
      try {
        var project = repo.get("projects", ws, Long.valueOf(projectId.toString()));
        context.put("projectId", project.get("id"));
        context.put("projectName", project.get("name"));
      } catch (RuntimeException ignored) {
        // A deleted or foreign project reference is simply left out.
      }
    }
    if (appointmentId != null) {
      var visit = repo.get("appointments", ws, appointmentId);
      var project = repo.get("projects", ws, Long.valueOf(visit.get("projectId").toString()));
      Instant at = Instant.parse(visit.get("scheduledAt").toString());
      List<Map<String, Object>> agent =
          db.queryForList("SELECT name, phone FROM users WHERE id=:id", Map.of("id", Long.valueOf(visit.get("agentId").toString())));
      Map<String, Object> details = new LinkedHashMap<>();
      details.put("appointmentId", visit.get("id"));
      details.put("projectId", project.get("id"));
      details.put("projectName", project.get("name"));
      details.put("address", project.get("location"));
      details.put("scheduledAt", at.toString());
      details.put("scheduledAtLocal", at.atZone(CallingHours.IST).toOffsetDateTime().toString());
      details.put("spokenTime", spokenTime(at));
      details.put("status", visit.get("status"));
      details.put("agentName", agent.isEmpty() ? null : agent.getFirst().get("name"));
      context.put("visit", details);
      context.putIfAbsent("projectId", project.get("id"));
      context.putIfAbsent("projectName", project.get("name"));
    }
    if (callbackId != null) {
      var callback = repo.get("callbacks", ws, callbackId);
      context.put("callback", Map.of("callbackId", callback.get("id"), "reason",
          Objects.requireNonNullElse(callback.get("reason"), ""), "requestedBy", callback.get("requestedBy")));
    }
    return context;
  }
}
