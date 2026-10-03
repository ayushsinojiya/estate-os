package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.calls.CallScheduleService;
import com.estraos.dto.Requests;
import com.estraos.exception.ApiException;
import com.estraos.mapper.DtoMapper;
import com.estraos.repository.TenantRepository;
import com.estraos.security.TenantContext;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Callbacks and the voice agent's partial lead updates. */
@Service
public class VoiceCrmService {
  private final TenantRepository repo;
  private final TenantContext tenant;
  private final DtoMapper mapper;
  private final CallScheduleService schedule;
  private final AuditService audit;

  public VoiceCrmService(TenantRepository repo, TenantContext tenant, DtoMapper mapper,
                         CallScheduleService schedule, AuditService audit) {
    this.repo = repo;
    this.tenant = tenant;
    this.mapper = mapper;
    this.schedule = schedule;
    this.audit = audit;
  }

  private void activity(Long ws, Long lead, String action, String description) {
    repo.event("lead_activities", ws, "lead_id", lead,
        EstateService.fields("action", action, "description", description, "userId", tenant.user()));
  }

  // ---------------------------------------------------------------- callbacks

  @Transactional
  public Map<String, Object> createCallback(Long ws, Long leadId, Instant dueAt, String reason, String requestedBy) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    repo.get("leads", ws, leadId);
    if (dueAt.isBefore(Instant.now().minusSeconds(60))) throw ApiException.bad("A callback must be in the future");
    var saved = repo.save("callbacks", ws, null, EstateService.fields("source", requestedBy == null ? "AGENT" : requestedBy),
        EstateService.fields("lead_id", leadId, "due_at", Timestamp.from(dueAt), "reason", reason,
            "requested_by", requestedBy == null ? "AGENT" : requestedBy, "status", "SCHEDULED"));
    Long id = EstateService.id(saved.get("id"));
    // The dispatcher defers a callback due outside calling hours to the next window.
    schedule.callback(ws, id, leadId, dueAt);
    activity(ws, leadId, "CALLBACK_SCHEDULED", "Callback scheduled for " + dueAt);
    audit.record(ws, tenant.user(), "CALLBACK_SCHEDULED", "LEAD", leadId);
    return saved;
  }

  public List<Map<String, Object>> callbacks(Long ws, Long leadId) {
    tenant.require(ws);
    repo.get("leads", ws, leadId);
    return repo.sql().query("SELECT * FROM callbacks WHERE workspace_id=:ws AND lead_id=:lead ORDER BY due_at DESC",
        Map.of("ws", ws, "lead", leadId), repo::row);
  }

  @Transactional
  public Map<String, Object> cancelCallback(Long ws, Long id) {
    tenant.require(ws);
    var callback = repo.get("callbacks", ws, id);
    if (!Set.of("SCHEDULED", "FAILED").contains(callback.get("status")))
      throw ApiException.conflict("Only a scheduled callback can be cancelled");
    var saved = repo.save("callbacks", ws, id, new LinkedHashMap<>(callback), EstateService.fields("status", "CANCELLED"));
    schedule.cancelCallback(ws, id);
    activity(ws, EstateService.id(callback.get("leadId")), "CALLBACK_CANCELLED", "Callback cancelled");
    return saved;
  }

  // ---------------------------------------------------------------- lead merge

  /**
   * Merges only the fields that were sent into the lead; status moves forward only. Each change is
   * recorded in lead_preferences, and a status change in lead_status_history.
   */
  @Transactional
  public Map<String, Object> patchLead(Long ws, Long leadId, Requests.LeadPatch patch) {
    tenant.require(ws);
    repo.workspaceLock(ws);
    var lead = repo.get("leads", ws, leadId);
    Map<String, Object> changes = new LinkedHashMap<>();
    Map<String, Object> raw = mapper.map(patch);
    raw.forEach((key, value) -> {
      if (value != null && !Set.of("name", "email", "status", "note").contains(key)) changes.put(key, value);
    });
    if (patch.language() != null && !Set.of("en", "hi", "mr", "gu").contains(patch.language()))
      throw ApiException.bad("Language must be en, hi, gu or mr");
    if (patch.budgetMin() != null && patch.budgetMax() != null && patch.budgetMin().compareTo(patch.budgetMax()) > 0)
      throw ApiException.bad("Budget minimum cannot exceed maximum");
    if (patch.projectId() != null) {
      repo.get("projects", ws, patch.projectId());
      changes.put("projectId", patch.projectId().toString());
    }
    if (patch.whatsappConsent() != null) changes.put("whatsappConsentAt", Instant.now().toString());
    String current = String.valueOf(lead.get("status"));
    String next = current;
    if (patch.status() != null) {
      if (!LeadStatus.valid(patch.status())) throw ApiException.bad("Unsupported status: " + patch.status());
      next = LeadStatus.advance(current, patch.status());
    }
    Map<String, Object> columns = new LinkedHashMap<>();
    if (patch.name() != null && !patch.name().isBlank()) columns.put("name", patch.name().trim());
    if (patch.email() != null) columns.put("email", patch.email().trim().toLowerCase(Locale.ROOT));
    columns.put("status", next);
    Map<String, Object> data = new LinkedHashMap<>(lead);
    data.putAll(changes);
    var saved = repo.save("leads", ws, leadId, data, columns);
    if (!changes.isEmpty()) repo.event("lead_preferences", ws, "lead_id", leadId, changes);
    if (!next.equals(current))
      repo.event("lead_status_history", ws, "lead_id", leadId,
          EstateService.fields("from", current, "to", next, "reason", "Voice agent update"));
    if (patch.note() != null && !patch.note().isBlank())
      repo.event("lead_notes", ws, "lead_id", leadId, EstateService.fields("text", patch.note(), "userId", tenant.user()));
    activity(ws, leadId, "LEAD_UPDATED", "Lead updated during a call (" + String.join(", ", changes.keySet()) + ")");
    audit.record(ws, tenant.user(), "LEAD_UPDATED", "LEAD", leadId);
    return saved;
  }
}
