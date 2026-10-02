package com.estraos.service;

import com.estraos.exception.ApiException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * Chooses a sales agent with no human in the loop.
 *
 * <p>Candidates are the project's assigned agents ({@code project_agents}) who are available for
 * the project and not on leave; a project with no assigned agents falls back to every available
 * REAL_ESTATE_AGENT in the workspace. Among them the one assigned longest ago goes first
 * (round-robin), skipping anyone with an overlapping active appointment. When nobody is free the
 * least-loaded candidate that day is returned with {@code flagged=true}, for a manager to review.
 * Callers hold the workspace lock, so two bookings cannot pick the same free agent concurrently.
 */
@Service
public class AgentAssignment {
  private final NamedParameterJdbcTemplate db;

  public AgentAssignment(NamedParameterJdbcTemplate db) {
    this.db = db;
  }

  public record Choice(Long userId, String name, String phone, boolean flagged, boolean projectAgent) {}

  private static final String ELIGIBLE =
      " JOIN users u ON u.id=m.user_id JOIN roles r ON r.id=m.role_id WHERE m.workspace_id=:ws AND"
          + " u.enabled AND r.name='REAL_ESTATE_AGENT' AND m.agent_available";

  private List<Map<String, Object>> candidates(Long ws, Long projectId) {
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    if (projectId != null) {
      params.put("project", projectId);
      Integer configured =
          db.queryForObject(
              "SELECT count(*) FROM project_agents WHERE workspace_id=:ws AND project_id=:project",
              params, Integer.class);
      if (configured != null && configured > 0)
        return db.queryForList(
            "SELECT m.user_id, u.name, u.phone, pa.last_assigned_at, true AS project_agent"
                + " FROM project_agents pa JOIN workspace_members m ON m.workspace_id=pa.workspace_id"
                + " AND m.user_id=pa.user_id"
                + ELIGIBLE
                + " AND pa.project_id=:project AND pa.available"
                + " ORDER BY pa.last_assigned_at NULLS FIRST, m.user_id",
            params);
    }
    // No agents configured for the project: share visits across the workspace's agents, rotating
    // by when each was last given an automatic assignment.
    return db.queryForList(
        "SELECT m.user_id, u.name, u.phone, (SELECT max(a.created_at) FROM appointments a WHERE"
            + " a.workspace_id=m.workspace_id AND a.agent_id=m.user_id AND a.data->>'assignedBy'='AUTO')"
            + " AS last_assigned_at, false AS project_agent FROM workspace_members m"
            + ELIGIBLE
            + " ORDER BY 4 NULLS FIRST, m.user_id",
        params);
  }

  private boolean busy(Long ws, Long agent, Instant start, Instant end, Long exceptAppointment) {
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("agent", agent);
    params.put("start", Timestamp.from(start));
    params.put("end", Timestamp.from(end));
    params.put("id", exceptAppointment == null ? 0L : exceptAppointment);
    Long n =
        db.queryForObject(
            "SELECT count(*) FROM appointments WHERE workspace_id=:ws AND id<>:id AND agent_id=:agent"
                + " AND status IN ('REQUESTED','CONFIRMED','RESCHEDULED') AND scheduled_at<:end AND"
                + " scheduled_at+duration_minutes*interval '1 minute'>:start",
            params,
            Long.class);
    return n != null && n > 0;
  }

  private long load(Long ws, Long agent, Instant dayStart, Instant dayEnd) {
    Long n =
        db.queryForObject(
            "SELECT count(*) FROM appointments WHERE workspace_id=:ws AND agent_id=:agent AND status"
                + " IN ('REQUESTED','CONFIRMED','RESCHEDULED') AND scheduled_at>=:from AND scheduled_at<:to",
            Map.of("ws", ws, "agent", agent, "from", Timestamp.from(dayStart), "to", Timestamp.from(dayEnd)),
            Long.class);
    return n == null ? 0 : n;
  }

  /**
   * An agent for a visit in [start, end). {@code keep} is tried first (a reschedule keeps its
   * agent when they are still free).
   */
  public Choice forVisit(Long ws, Long projectId, Instant start, Instant end, Long keep, Long exceptAppointment) {
    var candidates = candidates(ws, projectId);
    if (candidates.isEmpty())
      throw new ApiException(409, "NO_AGENT_AVAILABLE",
          "No sales agent is available to take site visits in this workspace");
    if (keep != null)
      for (var c : candidates)
        if (keep.equals(((Number) c.get("user_id")).longValue()) && !busy(ws, keep, start, end, exceptAppointment))
          return choice(c, false);
    for (var c : candidates) {
      Long agent = ((Number) c.get("user_id")).longValue();
      if (!busy(ws, agent, start, end, exceptAppointment)) return choice(c, false);
    }
    var day = start.atZone(com.estraos.calls.CallingHours.IST).toLocalDate();
    Instant dayStart = day.atStartOfDay(com.estraos.calls.CallingHours.IST).toInstant();
    Instant dayEnd = day.plusDays(1).atStartOfDay(com.estraos.calls.CallingHours.IST).toInstant();
    var least =
        candidates.stream()
            .min(Comparator.comparingLong(c -> load(ws, ((Number) c.get("user_id")).longValue(), dayStart, dayEnd)))
            .orElseThrow();
    return choice(least, true);
  }

  /** An agent for follow-up work (a handover) with no time slot: round-robin, no overlap check. */
  public Choice forHandover(Long ws, Long projectId, Long preferred) {
    var candidates = candidates(ws, projectId);
    if (preferred != null)
      for (var c : candidates)
        if (preferred.equals(((Number) c.get("user_id")).longValue())) return choice(c, false);
    if (candidates.isEmpty())
      throw new ApiException(409, "NO_AGENT_AVAILABLE", "No sales agent is available for a handover");
    return choice(candidates.getFirst(), false);
  }

  /** Moves the round-robin pointer past the chosen agent. */
  public void assigned(Long ws, Long projectId, Choice choice) {
    if (projectId == null || !choice.projectAgent()) return;
    db.update(
        "UPDATE project_agents SET last_assigned_at=now(), updated_at=now() WHERE workspace_id=:ws AND"
            + " project_id=:project AND user_id=:user",
        Map.of("ws", ws, "project", projectId, "user", choice.userId()));
  }

  private static Choice choice(Map<String, Object> row, boolean flagged) {
    return new Choice(
        ((Number) row.get("user_id")).longValue(),
        (String) row.get("name"),
        (String) row.get("phone"),
        flagged,
        Boolean.TRUE.equals(row.get("project_agent")));
  }
}
