package com.estraos.calls;

import com.estraos.audit.AuditService;
import com.estraos.exception.ApiException;
import com.estraos.integration.ExternalServiceException;
import com.estraos.mapper.DtoMapper;
import com.estraos.repository.TenantRepository;
import com.estraos.service.DncService;
import com.estraos.service.WhatsAppService;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Places scheduled outbound calls through the voice agent.
 *
 * <p>Due rows are claimed with {@code FOR UPDATE SKIP LOCKED} and dialled inside the claiming
 * transaction, so several API replicas never dial the same row; the row's idempotency key is the
 * agent request id, so a retry after a timeout cannot place a second call either. Before dialling:
 * do-not-call → SKIPPED; outside the TRAI window (09:00–21:00 IST) → deferred to 09:30; the lead
 * already called its daily cap today → deferred to tomorrow; a reminder for a visit that is no
 * longer active, or that would land within 30 minutes of the visit → SKIPPED.
 */
@Service
public class OutboundCallScheduler {
  private static final Logger log = LoggerFactory.getLogger(OutboundCallScheduler.class);
  private final JdbcTemplate jdbc;
  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final DtoMapper mapper;
  private final OutboundCallService outbound;
  private final CallScheduleService schedule;
  private final CallingHours hours;
  private final DncService dnc;
  private final WhatsAppService whatsapp;
  private final AuditService audit;
  private final int dailyCap;
  private final int maxAttempts;
  private final int reengageAfterDays;
  private final int reengageMaxAttempts;

  public OutboundCallScheduler(JdbcTemplate jdbc, NamedParameterJdbcTemplate db, TenantRepository repo,
      DtoMapper mapper, OutboundCallService outbound, CallScheduleService schedule, CallingHours hours,
      DncService dnc, WhatsAppService whatsapp, AuditService audit,
      @Value("${app.calls.daily-attempt-cap:2}") int dailyCap,
      @Value("${app.calls.max-attempts:3}") int maxAttempts,
      @Value("${app.calls.reengage-after-days:7}") int reengageAfterDays,
      @Value("${app.calls.reengage-max-attempts:2}") int reengageMaxAttempts) {
    this.jdbc = jdbc;
    this.db = db;
    this.repo = repo;
    this.mapper = mapper;
    this.outbound = outbound;
    this.schedule = schedule;
    this.hours = hours;
    this.dnc = dnc;
    this.whatsapp = whatsapp;
    this.audit = audit;
    this.dailyCap = dailyCap;
    this.maxAttempts = maxAttempts;
    this.reengageAfterDays = reengageAfterDays;
    this.reengageMaxAttempts = reengageMaxAttempts;
  }

  /** Dispatches due calls. Returns how many were dialled. */
  @Transactional
  public int dispatchDue() {
    return dispatchDue(Instant.now());
  }

  @Transactional
  public int dispatchDue(Instant now) {
    var rows = jdbc.queryForList(
        "SELECT id, workspace_id, lead_id, call_type, due_at, idempotency_key, appointment_id, callback_id,"
            + " attempts, data FROM scheduled_calls WHERE status='SCHEDULED' AND due_at <= ?"
            + " ORDER BY due_at, id LIMIT 20 FOR UPDATE SKIP LOCKED", Timestamp.from(now));
    int dialled = 0;
    for (var row : rows) {
      try {
        if (dispatch(row, now)) dialled++;
      } catch (RuntimeException e) {
        log.error("Scheduled call {} could not be processed", row.get("id"), e);
        mark(row, "FAILED", Map.of("failure", e.getClass().getSimpleName()));
      }
    }
    return dialled;
  }

  private Long lng(Object value) {
    return value == null ? null : ((Number) value).longValue();
  }

  private void mark(Map<String, Object> row, String status, Map<String, Object> extra) {
    db.update("UPDATE scheduled_calls SET status=:status, updated_at=now(), data=data||CAST(:extra AS jsonb)"
            + " WHERE id=:id",
        Map.of("status", status, "extra", mapper.write(extra), "id", lng(row.get("id"))));
  }

  private void defer(Map<String, Object> row, Instant due, String reason) {
    db.update("UPDATE scheduled_calls SET due_at=:due, updated_at=now(), data=data||jsonb_build_object("
            + "'deferredReason', CAST(:reason AS text)) WHERE id=:id",
        Map.of("due", Timestamp.from(due), "reason", reason, "id", lng(row.get("id"))));
  }

  private int callsToday(Long ws, Long lead, Instant now) {
    Instant from = hours.startOfDay(now);
    Integer n = db.queryForObject(
        "SELECT count(*) FROM voice_sessions WHERE workspace_id=:ws AND lead_id=:lead AND"
            + " data->>'outbound'='true' AND (data->>'dialedAt')::timestamptz >= :from AND"
            + " (data->>'dialedAt')::timestamptz < :to",
        Map.of("ws", ws, "lead", lead, "from", Timestamp.from(from),
            "to", Timestamp.from(from.plus(Duration.ofDays(1)))), Integer.class);
    return n == null ? 0 : n;
  }

  private boolean dispatch(Map<String, Object> row, Instant now) {
    Long ws = lng(row.get("workspace_id"));
    Long leadId = lng(row.get("lead_id"));
    String type = (String) row.get("call_type");
    Long appointment = lng(row.get("appointment_id"));
    Long callback = lng(row.get("callback_id"));
    var lead = repo.get("leads", ws, leadId);
    if (Boolean.TRUE.equals(lead.get("doNotCall")) || dnc.listed(ws, String.valueOf(lead.get("phone")))) {
      mark(row, "SKIPPED", Map.of("skipReason", "DO_NOT_CALL"));
      return false;
    }
    Instant visitAt = null;
    if (appointment != null) {
      var visit = repo.get("appointments", ws, appointment);
      if (!Set.of("REQUESTED", "CONFIRMED", "RESCHEDULED").contains(visit.get("status"))) {
        mark(row, "SKIPPED", Map.of("skipReason", "VISIT_NOT_ACTIVE"));
        return false;
      }
      visitAt = Instant.parse(visit.get("scheduledAt").toString());
    }
    if (!hours.allows(now)) {
      Instant next = hours.clamp(now);
      if (visitAt != null && !next.isBefore(visitAt.minus(Duration.ofMinutes(30)))) {
        mark(row, "SKIPPED", Map.of("skipReason", "TOO_CLOSE_TO_VISIT"));
        return false;
      }
      defer(row, next, "OUTSIDE_CALLING_HOURS");
      return false;
    }
    if (callsToday(ws, leadId, now) >= dailyCap) {
      Instant tomorrow = hours.clamp(hours.startOfDay(now).plus(Duration.ofDays(1)));
      if (visitAt != null && !tomorrow.isBefore(visitAt)) {
        mark(row, "SKIPPED", Map.of("skipReason", "DAILY_CAP"));
        return false;
      }
      defer(row, tomorrow, "DAILY_CAP");
      return false;
    }
    try {
      var session = outbound.start(ws, lead, type, appointment, callback, (String) row.get("idempotency_key"), null, now);
      mark(row, "DIALING", Map.of("dialedAt", now.toString(), "voiceSessionId", session.get("id"),
          "externalId", Objects.requireNonNullElse(session.get("externalId"), "")));
      if (callback != null)
        db.update("UPDATE callbacks SET status='DIALING', attempts=attempts+1, updated_at=now() WHERE"
            + " workspace_id=:ws AND id=:id", Map.of("ws", ws, "id", callback));
      if (appointment != null && "DAY_BEFORE".equals(mapper.read(row.get("data").toString()).get("reminder")))
        whatsapp.visitReminder(ws, appointment); // only with the customer's consent; never throws
      return true;
    } catch (ApiException e) {
      if ("DO_NOT_CALL".equals(e.code)) {
        mark(row, "SKIPPED", Map.of("skipReason", "DO_NOT_CALL"));
        return false;
      }
      throw e;
    } catch (ExternalServiceException e) {
      int attempts = ((Number) row.get("attempts")).intValue() + 1;
      audit.record(ws, null, "EXTERNAL_SERVICE_FAILED", "SCHEDULED_CALL", lng(row.get("id")));
      if (attempts >= maxAttempts) {
        db.update("UPDATE scheduled_calls SET status='FAILED', attempts=:a, updated_at=now() WHERE id=:id",
            Map.of("a", attempts, "id", lng(row.get("id"))));
        if (callback != null)
          db.update("UPDATE callbacks SET status='FAILED', updated_at=now() WHERE workspace_id=:ws AND id=:id",
              Map.of("ws", ws, "id", callback));
      } else {
        db.update("UPDATE scheduled_calls SET attempts=:a, due_at=:due, updated_at=now() WHERE id=:id",
            Map.of("a", attempts, "due", Timestamp.from(hours.clamp(now.plus(Duration.ofMinutes(5L * attempts)))),
                "id", lng(row.get("id"))));
      }
      return false;
    }
  }

  /**
   * Leads in CONTACTED or QUALIFIED with no activity for N days get a re-engagement call, at most
   * twice. The dispatcher applies calling hours and the daily cap when they fall due.
   */
  @Transactional
  public int scheduleReengagement() {
    var leads = jdbc.queryForList(
        "SELECT l.workspace_id, l.id FROM leads l WHERE l.deleted_at IS NULL"
            + " AND l.status IN ('CONTACTED','QUALIFIED') AND"
            + " coalesce((l.data->>'doNotCall')::boolean, false) = false AND l.updated_at < now() - make_interval(days => ?)"
            + " AND NOT EXISTS (SELECT 1 FROM lead_activities a WHERE a.workspace_id=l.workspace_id AND"
            + "  a.lead_id=l.id AND a.created_at > now() - make_interval(days => ?))"
            + " AND NOT EXISTS (SELECT 1 FROM scheduled_calls s WHERE s.workspace_id=l.workspace_id AND"
            + "  s.lead_id=l.id AND s.status IN ('SCHEDULED','DIALING'))"
            + " AND (SELECT count(*) FROM scheduled_calls s WHERE s.workspace_id=l.workspace_id AND"
            + "  s.lead_id=l.id AND s.call_type='RE_ENGAGEMENT') < ? ORDER BY l.updated_at LIMIT 100",
        reengageAfterDays, reengageAfterDays, reengageMaxAttempts);
    int created = 0;
    for (var lead : leads) {
      Long ws = lng(lead.get("workspace_id"));
      Long id = lng(lead.get("id"));
      Integer previous = db.queryForObject("SELECT count(*) FROM scheduled_calls WHERE workspace_id=:ws AND"
          + " lead_id=:id AND call_type='RE_ENGAGEMENT'", Map.of("ws", ws, "id", id), Integer.class);
      if (schedule.reengagement(ws, id, (previous == null ? 0 : previous) + 1)) created++;
    }
    return created;
  }
}
