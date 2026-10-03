package com.estraos.calls;

import com.estraos.audit.AuditService;
import com.estraos.exception.ApiException;
import com.estraos.integration.VoiceAgentServiceClient;
import com.estraos.repository.TenantRepository;
import com.estraos.service.DncService;
import com.estraos.service.EstateService;
import java.util.*;
import org.springframework.stereotype.Service;

/**
 * Asks the voice agent to place one outbound call and records it. Used by the CRM's "call now"
 * action and by the scheduler. A number on the do-not-call list is refused here, before anything
 * reaches the agent, with 409.
 */
@Service
public class OutboundCallService {
  private final TenantRepository repo;
  private final VoiceAgentServiceClient voice;
  private final DncService dnc;
  private final CallScheduleService schedule;
  private final AuditService audit;

  public OutboundCallService(TenantRepository repo, VoiceAgentServiceClient voice, DncService dnc,
                             CallScheduleService schedule, AuditService audit) {
    this.repo = repo;
    this.voice = voice;
    this.dnc = dnc;
    this.schedule = schedule;
    this.audit = audit;
  }

  public static ApiException doNotCall() {
    return new ApiException(409, "DO_NOT_CALL", "This number is on the do-not-call list");
  }

  public void refuseIfDnc(Long ws, Map<String, Object> lead) {
    if (Boolean.TRUE.equals(lead.get("doNotCall")) || dnc.listed(ws, String.valueOf(lead.get("phone"))))
      throw doNotCall();
  }

  /** Throws ExternalServiceException when the agent cannot be reached; the caller decides what that means. */
  public Map<String, Object> start(Long ws, Map<String, Object> lead, String callType, Long appointmentId,
                                   Long callbackId, String requestId, Long actor) {
    return start(ws, lead, callType, appointmentId, callbackId, requestId, actor, java.time.Instant.now());
  }

  /** {@code dialedAt} is when the call is placed; the scheduler's daily cap counts by it. */
  public Map<String, Object> start(Long ws, Map<String, Object> lead, String callType, Long appointmentId,
                                   Long callbackId, String requestId, Long actor, java.time.Instant dialedAt) {
    refuseIfDnc(ws, lead);
    Long leadId = EstateService.id(lead.get("id"));
    Map<String, Object> context = schedule.context(ws, lead, appointmentId, callbackId);
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("workspaceId", ws.toString());
    payload.put("leadId", leadId.toString());
    payload.put("phone", lead.get("phone"));
    payload.put("language", Objects.requireNonNullElse(lead.get("language"), "en"));
    payload.put("requestId", requestId);
    payload.put("callType", callType);
    if (appointmentId != null) payload.put("appointmentId", appointmentId.toString());
    if (callbackId != null) payload.put("callbackId", callbackId.toString());
    if (context.get("projectId") != null) payload.put("projectId", context.get("projectId").toString());
    payload.put("context", context);
    Map<String, Object> result = new LinkedHashMap<>(voice.startOutboundCall(payload));
    result.put("leadName", lead.get("name"));
    result.put("callType", callType);
    result.put("direction", "outbound");
    result.put("outbound", true);
    result.put("requestId", requestId);
    result.put("dialedAt", dialedAt.toString());
    if (appointmentId != null) result.put("appointmentId", appointmentId.toString());
    if (callbackId != null) result.put("callbackId", callbackId.toString());
    var saved = repo.save("voice_sessions", ws, null, result,
        EstateService.fields("lead_id", leadId, "status", result.getOrDefault("status", "QUEUED")));
    Long session = EstateService.id(saved.get("id"));
    repo.event("voice_session_events", ws, "voice_session_id", session,
        EstateService.fields("status", result.get("status"), "outcome", result.get("outcome")));
    for (String[] pair : new String[][] {{"voice_transcripts", "transcript"}, {"voice_summaries", "summary"},
        {"voice_session_requirements", "requirements"}})
      if (result.get(pair[1]) != null)
        repo.event(pair[0], ws, "voice_session_id", session, EstateService.fields(pair[1], result.get(pair[1])));
    repo.event("lead_activities", ws, "lead_id", leadId, EstateService.fields(
        "action", "CALL_STARTED", "description", "Outbound call requested (" + callType + ")", "userId", actor));
    audit.record(ws, actor, "CALL_STARTED", "VOICE_SESSION", session);
    return saved;
  }
}
