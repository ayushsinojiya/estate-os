package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.calls.CallScheduleService;
import com.estraos.calls.CallingHours;
import com.estraos.dto.Requests;
import com.estraos.exception.ApiException;
import com.estraos.repository.TenantRepository;
import com.estraos.security.TenantContext;
import java.sql.Time;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Bookable site-visit slots, computed rather than stored: weekly templates (the project's own, else
 * the workspace default, else Mon–Sun 10:00–19:00 in 60-minute slots of capacity 3), minus
 * blackouts, minus the capacity active appointments already take. Times are Asia/Kolkata.
 *
 * <p>Voice bookings run under the workspace lock, re-check the slot, assign an agent
 * ({@link AgentAssignment}) and save through {@link EstateService#saveVisit}, so the usual
 * validation, overlap check, history, notifications and reminders all apply.
 */
@Service
public class VisitSlotService {
  public static final List<Requests.SlotWindow> DEFAULT =
      List.of(new Requests.SlotWindow(List.of(1, 2, 3, 4, 5, 6, 7), LocalTime.of(10, 0), LocalTime.of(19, 0), 60, 3));
  private static final Set<String> ACTIVE = Set.of("REQUESTED", "CONFIRMED", "RESCHEDULED");

  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final TenantContext tenant;
  private final EstateService estate;
  private final AgentAssignment agents;
  private final AuditService audit;
  private final long minLeadMinutes;

  public VisitSlotService(NamedParameterJdbcTemplate db, TenantRepository repo, TenantContext tenant,
                          EstateService estate, AgentAssignment agents, AuditService audit,
                          @Value("${app.visits.min-lead-minutes:60}") long minLeadMinutes) {
    this.db = db;
    this.repo = repo;
    this.tenant = tenant;
    this.estate = estate;
    this.agents = agents;
    this.audit = audit;
    this.minLeadMinutes = minLeadMinutes;
  }

  record Window(int day, LocalTime start, LocalTime end, int minutes, int capacity) {}

  record Slot(Instant start, Instant end, int capacity, int booked) {
    int remaining() {
      return capacity - booked;
    }
  }

  // ---------------------------------------------------------------- templates

  private List<Window> rows(Long ws, Long projectId) {
    String scope = projectId == null ? "project_id IS NULL" : "project_id=:project";
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("project", projectId);
    return db.query("SELECT day_of_week, start_time, end_time, slot_minutes, capacity FROM visit_slot_templates"
            + " WHERE workspace_id=:ws AND " + scope + " ORDER BY day_of_week, start_time", params,
        (rs, n) -> new Window(rs.getInt("day_of_week"), rs.getTime("start_time").toLocalTime(),
            rs.getTime("end_time").toLocalTime(), rs.getInt("slot_minutes"), rs.getInt("capacity")));
  }

  private static List<Window> expand(List<Requests.SlotWindow> windows) {
    List<Window> out = new ArrayList<>();
    for (var w : windows)
      for (int day : new TreeSet<>(w.days())) out.add(new Window(day, w.start(), w.end(), w.slotMinutes(), w.capacity()));
    return out;
  }

  /** The windows in force for a project and where they come from: PROJECT, WORKSPACE or DEFAULT. */
  private Map.Entry<String, List<Window>> effective(Long ws, Long projectId) {
    var own = projectId == null ? List.<Window>of() : rows(ws, projectId);
    if (!own.isEmpty()) return Map.entry("PROJECT", own);
    var shared = rows(ws, null);
    if (!shared.isEmpty()) return Map.entry("WORKSPACE", shared);
    return Map.entry("DEFAULT", expand(DEFAULT));
  }

  /** Windows grouped back into editable form: same hours, minutes and capacity → one row of days. */
  private static List<Map<String, Object>> grouped(List<Window> windows) {
    Map<List<Object>, List<Integer>> groups = new LinkedHashMap<>();
    for (var w : windows)
      groups.computeIfAbsent(List.of(w.start(), w.end(), w.minutes(), w.capacity()), k -> new ArrayList<>()).add(w.day());
    List<Map<String, Object>> out = new ArrayList<>();
    groups.forEach((key, days) -> out.add(EstateService.fields("days", days, "start", key.get(0).toString(),
        "end", key.get(1).toString(), "slotMinutes", key.get(2), "capacity", key.get(3))));
    return out;
  }

  public Map<String, Object> templates(Long ws, Long projectId) {
    tenant.require(ws);
    if (projectId != null) repo.get("projects", ws, projectId);
    var effective = effective(ws, projectId);
    return EstateService.fields("projectId", projectId == null ? null : projectId.toString(),
        "source", effective.getKey(), "timezone", CallingHours.IST.getId(), "windows", grouped(effective.getValue()));
  }

  @Transactional
  public Map<String, Object> saveTemplates(Long ws, Long projectId, Requests.SlotTemplates request) {
    tenant.manage(ws);
    if (projectId != null) repo.get("projects", ws, projectId);
    for (var w : request.windows()) {
      if (!w.end().isAfter(w.start())) throw ApiException.bad("Visiting hours must end after they start");
      if (Duration.between(w.start(), w.end()).toMinutes() < w.slotMinutes())
        throw ApiException.bad("A window must fit at least one slot");
    }
    var expanded = expand(request.windows());
    Set<String> seen = new HashSet<>();
    for (var a : expanded)
      for (var b : expanded)
        if (a != b && a.day() == b.day() && a.start().isBefore(b.end()) && b.start().isBefore(a.end())
            && seen.add(a.day() + ":" + a.start()))
          throw ApiException.bad("Visiting windows overlap on the same day");
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("project", projectId);
    db.update("DELETE FROM visit_slot_templates WHERE workspace_id=:ws AND "
        + (projectId == null ? "project_id IS NULL" : "project_id=:project"), params);
    for (var w : expanded) {
      Map<String, Object> row = new HashMap<>(params);
      row.put("day", w.day());
      row.put("start", Time.valueOf(w.start()));
      row.put("end", Time.valueOf(w.end()));
      row.put("minutes", w.minutes());
      row.put("capacity", w.capacity());
      db.update("INSERT INTO visit_slot_templates(workspace_id,project_id,day_of_week,start_time,end_time,"
          + "slot_minutes,capacity) VALUES (:ws,:project,:day,:start,:end,:minutes,:capacity)", row);
    }
    audit.record(ws, tenant.user(), "VISIT_SLOTS_UPDATED", "PROJECT", projectId);
    return templates(ws, projectId);
  }

  // ---------------------------------------------------------------- blackouts

  public List<Map<String, Object>> blackouts(Long ws, Long projectId) {
    tenant.require(ws);
    repo.get("projects", ws, projectId);
    return repo.sql().query("SELECT * FROM visit_slot_blackouts WHERE workspace_id=:ws AND (project_id=:project"
            + " OR project_id IS NULL) AND ends_at > now() ORDER BY starts_at",
        Map.of("ws", ws, "project", projectId), repo::row);
  }

  @Transactional
  public Map<String, Object> addBlackout(Long ws, Long projectId, Requests.Blackout request) {
    tenant.manage(ws);
    if (projectId != null) repo.get("projects", ws, projectId);
    if (!request.endsAt().isAfter(request.startsAt())) throw ApiException.bad("A closure must end after it starts");
    var saved = repo.save("visit_slot_blackouts", ws, null, EstateService.fields("reason", request.reason()),
        EstateService.fields("project_id", projectId, "starts_at", Timestamp.from(request.startsAt()),
            "ends_at", Timestamp.from(request.endsAt())));
    audit.record(ws, tenant.user(), "VISIT_BLACKOUT_ADDED", "PROJECT", projectId);
    return saved;
  }

  @Transactional
  public void deleteBlackout(Long ws, Long id) {
    tenant.manage(ws);
    repo.get("visit_slot_blackouts", ws, id);
    db.update("DELETE FROM visit_slot_blackouts WHERE workspace_id=:ws AND id=:id", Map.of("ws", ws, "id", id));
    audit.record(ws, tenant.user(), "VISIT_BLACKOUT_REMOVED", "VISIT_BLACKOUT", id);
  }

  // ---------------------------------------------------------------- project agents

  public List<Map<String, Object>> projectAgents(Long ws, Long projectId) {
    tenant.require(ws);
    repo.get("projects", ws, projectId);
    return db.query("SELECT pa.user_id, u.name, u.email, u.phone, pa.available, m.agent_available,"
            + " pa.last_assigned_at FROM project_agents pa JOIN users u ON u.id=pa.user_id JOIN workspace_members m"
            + " ON m.workspace_id=pa.workspace_id AND m.user_id=pa.user_id WHERE pa.workspace_id=:ws AND"
            + " pa.project_id=:project ORDER BY u.name", Map.of("ws", ws, "project", projectId),
        (rs, n) -> {
          Map<String, Object> row = new LinkedHashMap<>();
          row.put("userId", rs.getString("user_id"));
          row.put("name", rs.getString("name"));
          row.put("email", rs.getString("email"));
          row.put("phone", rs.getString("phone"));
          row.put("available", rs.getBoolean("available"));
          row.put("agentAvailable", rs.getBoolean("agent_available"));
          Timestamp last = rs.getTimestamp("last_assigned_at");
          row.put("lastAssignedAt", last == null ? null : last.toInstant().toString());
          return row;
        });
  }

  @Transactional
  public List<Map<String, Object>> saveProjectAgents(Long ws, Long projectId, Requests.ProjectAgents request) {
    tenant.manage(ws);
    repo.get("projects", ws, projectId);
    Set<Long> keep = new HashSet<>();
    for (var agent : request.agents()) {
      tenant.member(ws, agent.userId()); // must be an active REAL_ESTATE_AGENT here
      keep.add(agent.userId());
      db.update("INSERT INTO project_agents(workspace_id,project_id,user_id,available) VALUES"
              + " (:ws,:project,:user,:available) ON CONFLICT (workspace_id,project_id,user_id) DO UPDATE SET"
              + " available=excluded.available, updated_at=now()",
          Map.of("ws", ws, "project", projectId, "user", agent.userId(),
              "available", agent.available() == null || agent.available()));
    }
    Map<String, Object> params = new HashMap<>(Map.of("ws", ws, "project", projectId));
    params.put("keep", keep.isEmpty() ? List.of(0L) : new ArrayList<>(keep));
    db.update("DELETE FROM project_agents WHERE workspace_id=:ws AND project_id=:project AND user_id NOT IN (:keep)", params);
    audit.record(ws, tenant.user(), "PROJECT_AGENTS_UPDATED", "PROJECT", projectId);
    return projectAgents(ws, projectId);
  }

  @Transactional
  public Map<String, Object> setAvailability(Long ws, Long userId, boolean available) {
    tenant.manage(ws);
    int n = db.update("UPDATE workspace_members SET agent_available=:available, updated_at=now() WHERE"
        + " workspace_id=:ws AND user_id=:user", Map.of("available", available, "ws", ws, "user", userId));
    if (n != 1) throw ApiException.missing();
    audit.record(ws, tenant.user(), available ? "AGENT_AVAILABLE" : "AGENT_UNAVAILABLE", "USER", userId);
    return EstateService.fields("userId", userId.toString(), "agentAvailable", available);
  }

  // ---------------------------------------------------------------- slots

  List<Slot> compute(Long ws, Long projectId, LocalDate from, int days, Long excludeAppointment) {
    var windows = effective(ws, projectId).getValue();
    Instant rangeStart = from.atStartOfDay(CallingHours.IST).toInstant();
    Instant rangeEnd = from.plusDays(days).atStartOfDay(CallingHours.IST).toInstant();
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("project", projectId);
    params.put("from", Timestamp.from(rangeStart));
    params.put("to", Timestamp.from(rangeEnd));
    params.put("except", excludeAppointment == null ? 0L : excludeAppointment);
    var closures = db.query("SELECT starts_at, ends_at FROM visit_slot_blackouts WHERE workspace_id=:ws AND"
            + " (project_id=:project OR project_id IS NULL) AND ends_at > :from AND starts_at < :to", params,
        (rs, n) -> new Instant[] {rs.getTimestamp("starts_at").toInstant(), rs.getTimestamp("ends_at").toInstant()});
    var booked = db.query("SELECT scheduled_at, duration_minutes FROM appointments WHERE workspace_id=:ws AND"
            + " project_id=:project AND id<>:except AND status IN ('REQUESTED','CONFIRMED','RESCHEDULED') AND"
            + " scheduled_at < :to AND scheduled_at + duration_minutes * interval '1 minute' > :from", params,
        (rs, n) -> {
          Instant s = rs.getTimestamp("scheduled_at").toInstant();
          return new Instant[] {s, s.plusSeconds(rs.getInt("duration_minutes") * 60L)};
        });
    Instant earliest = Instant.now().plus(Duration.ofMinutes(minLeadMinutes));
    List<Slot> out = new ArrayList<>();
    for (int d = 0; d < days; d++) {
      LocalDate date = from.plusDays(d);
      int dow = date.getDayOfWeek().getValue();
      for (var w : windows) {
        if (w.day() != dow) continue;
        int first = w.start().toSecondOfDay() / 60, last = w.end().toSecondOfDay() / 60;
        for (int minute = first; minute + w.minutes() <= last; minute += w.minutes()) {
          Instant start = date.atStartOfDay(CallingHours.IST).toLocalDateTime().plusMinutes(minute)
              .atZone(CallingHours.IST).toInstant();
          Instant end = start.plus(Duration.ofMinutes(w.minutes()));
          if (start.isBefore(earliest)) continue;
          if (closures.stream().anyMatch(c -> start.isBefore(c[1]) && c[0].isBefore(end))) continue;
          int taken = (int) booked.stream().filter(b -> start.isBefore(b[1]) && b[0].isBefore(end)).count();
          out.add(new Slot(start, end, w.capacity(), taken));
        }
      }
    }
    out.sort(Comparator.comparing(Slot::start));
    return out;
  }

  private static Map<String, Object> slotJson(Slot slot) {
    return EstateService.fields("start", slot.start().toString(), "end", slot.end().toString(),
        "startLocal", slot.start().atZone(CallingHours.IST).toOffsetDateTime().toString(),
        "label", CallScheduleService.spokenTime(slot.start()),
        "date", slot.start().atZone(CallingHours.IST).toLocalDate().toString(),
        "capacity", slot.capacity(), "remaining", slot.remaining());
  }

  /** Free slots from {@code from} (IST date, default today) for {@code days} days. */
  public Map<String, Object> slots(Long ws, Long projectId, LocalDate from, int days) {
    tenant.require(ws);
    if (days < 1 || days > 14) throw ApiException.bad("days must be between 1 and 14");
    var project = repo.get("projects", ws, projectId);
    LocalDate start = from == null ? LocalDate.now(CallingHours.IST) : from;
    List<Map<String, Object>> free = new ArrayList<>();
    if ("ACTIVE".equals(project.get("status")))
      for (var slot : compute(ws, projectId, start, days, null))
        if (slot.remaining() > 0) free.add(slotJson(slot));
    return EstateService.fields("projectId", projectId.toString(), "projectName", project.get("name"),
        "timezone", CallingHours.IST.getId(), "from", start.toString(), "days", days, "slots", free);
  }

  private Slot freeSlot(Long ws, Long projectId, Instant start, Long excludeAppointment) {
    LocalDate date = start.atZone(CallingHours.IST).toLocalDate();
    return compute(ws, projectId, date, 1, excludeAppointment).stream()
        .filter(s -> s.start().equals(start) && s.remaining() > 0).findFirst()
        .orElseThrow(() -> new ApiException(409, "SLOT_UNAVAILABLE", "That visit slot is no longer available"));
  }

  // ---------------------------------------------------------------- voice bookings

  private Map<String, Object> response(Map<String, Object> visit, AgentAssignment.Choice agent) {
    Map<String, Object> out = new LinkedHashMap<>(visit);
    Instant at = Instant.parse(visit.get("scheduledAt").toString());
    out.put("agentName", agent.name());
    out.put("agentPhone", agent.phone());
    out.put("scheduledAtLocal", at.atZone(CallingHours.IST).toOffsetDateTime().toString());
    out.put("spokenTime", CallScheduleService.spokenTime(at));
    return out;
  }

  /**
   * Books a visit into a slot. Serialised on the workspace lock, so two callers cannot both take a
   * slot's last place. The lead's status moves forward to VISIT_PLANNED.
   */
  @Transactional
  public Map<String, Object> book(Long ws, Requests.VoiceVisit request) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    repo.get("leads", ws, request.leadId());
    Slot slot = freeSlot(ws, request.projectId(), request.slotStart(), null);
    var agent = agents.forVisit(ws, request.projectId(), slot.start(), slot.end(), null, null);
    int minutes = (int) Duration.between(slot.start(), slot.end()).toMinutes();
    var visit = new Requests.Visit(request.leadId(), request.projectId(), request.unitId(), agent.userId(),
        slot.start(), minutes, request.notes(), agent.flagged() ? "REQUESTED" : "CONFIRMED", "PENDING");
    Map<String, Object> extra = EstateService.fields("bookedBy", "VOICE_AGENT", "assignedBy", "AUTO",
        "needsManagerReview", agent.flagged(), "callId", request.callId(),
        "bookingLanguage", request.language());
    var saved = estate.saveVisit(ws, null, visit, new EstateService.VisitOptions(agent.flagged(), true, extra,
        agent.flagged() ? "no agent is free for that slot; " + agent.name() + " was assigned provisionally" : null));
    agents.assigned(ws, request.projectId(), agent);
    return response(saved, agent);
  }

  private Map<String, Object> active(Long ws, Long id) {
    var visit = repo.get("appointments", ws, id);
    if (!ACTIVE.contains(visit.get("status")))
      throw new ApiException(409, "VISIT_NOT_ACTIVE", "This visit is " + visit.get("status").toString().toLowerCase(Locale.ROOT));
    return visit;
  }

  private Requests.Visit copy(Map<String, Object> visit, Instant at, int minutes, Long agent, String status,
                              String confirmation) {
    return new Requests.Visit(EstateService.id(visit.get("leadId")), EstateService.id(visit.get("projectId")),
        EstateService.id(visit.get("unitId")), agent, at, minutes, (String) visit.get("notes"), status, confirmation);
  }

  @Transactional
  public Map<String, Object> reschedule(Long ws, Long id, Requests.VisitReschedule request) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var visit = active(ws, id);
    Long project = EstateService.id(visit.get("projectId"));
    Slot slot = freeSlot(ws, project, request.slotStart(), id);
    var agent = agents.forVisit(ws, project, slot.start(), slot.end(), EstateService.id(visit.get("agentId")), id);
    int minutes = (int) Duration.between(slot.start(), slot.end()).toMinutes();
    var saved = estate.saveVisit(ws, id, copy(visit, slot.start(), minutes, agent.userId(), "RESCHEDULED", "PENDING"),
        new EstateService.VisitOptions(agent.flagged(), true, EstateService.fields(
            "rescheduledBy", "VOICE_AGENT", "rescheduleReason", request.reason(),
            "previousScheduledAt", visit.get("scheduledAt"), "needsManagerReview", agent.flagged()),
            agent.flagged() ? "rescheduled into a slot with no free agent" : null));
    agents.assigned(ws, project, agent);
    return response(saved, agent);
  }

  @Transactional
  public Map<String, Object> cancel(Long ws, Long id, Requests.VisitChange request) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var visit = active(ws, id);
    Long agentId = EstateService.id(visit.get("agentId"));
    var saved = estate.saveVisit(ws, id, copy(visit, Instant.parse(visit.get("scheduledAt").toString()),
            ((Number) visit.get("durationMinutes")).intValue(), agentId, "CANCELLED", "DECLINED"),
        new EstateService.VisitOptions(true, true, EstateService.fields("cancelledBy", "VOICE_AGENT",
            "cancelReason", request == null ? null : request.reason()), null));
    return response(saved, new AgentAssignment.Choice(agentId, null, null, false, false));
  }

  @Transactional
  public Map<String, Object> confirm(Long ws, Long id) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var visit = active(ws, id);
    Long agentId = EstateService.id(visit.get("agentId"));
    var saved = estate.saveVisit(ws, id, copy(visit, Instant.parse(visit.get("scheduledAt").toString()),
            ((Number) visit.get("durationMinutes")).intValue(), agentId, "CONFIRMED", "CONFIRMED"),
        new EstateService.VisitOptions(true, true, EstateService.fields("confirmedBy", "VOICE_AGENT",
            "confirmedAt", Instant.now().toString()), null));
    var rows = db.queryForList("SELECT name, phone FROM users WHERE id=:id", Map.of("id", agentId));
    return response(saved, new AgentAssignment.Choice(agentId, rows.isEmpty() ? null : (String) rows.getFirst().get("name"),
        rows.isEmpty() ? null : (String) rows.getFirst().get("phone"), false, false));
  }
}
