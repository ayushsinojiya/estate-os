package com.estraos.controller;

import com.estraos.dto.Requests;
import com.estraos.security.TenantContext;
import com.estraos.service.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Positive;
import java.time.LocalDate;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

/**
 * Write-side endpoints for the voice agent: slots, bookings, callbacks, do-not-call, lead merge.
 * The agent calls these as its service account; workspace membership is checked like any user.
 */
@RestController
@RequestMapping("/api/v1/voice")
@Validated
public class VoiceCrmController {
  private final VisitSlotService visits;
  private final VoiceCrmService crm;
  private final DncService dnc;
  private final TenantContext tenant;

  public VoiceCrmController(VisitSlotService visits, VoiceCrmService crm, DncService dnc, TenantContext tenant) {
    this.visits = visits;
    this.crm = crm;
    this.dnc = dnc;
    this.tenant = tenant;
  }

  /** Free slots, labelled for speech in IST ("Saturday 11 AM"). {@code from} is an IST date. */
  @GetMapping("/projects/{id}/slots")
  public Map<String, Object> slots(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam(required = false) LocalDate from,
      @RequestParam(defaultValue = "3") int days) {
    return visits.slots(ws, id, from, days);
  }

  @PostMapping("/visits")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> book(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.VoiceVisit body) {
    return visits.book(ws, body);
  }

  @PostMapping("/visits/{id}/reschedule")
  public Map<String, Object> reschedule(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.VisitReschedule body) {
    return visits.reschedule(ws, id, body);
  }

  @PostMapping("/visits/{id}/cancel")
  public Map<String, Object> cancel(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody(required = false) Requests.VisitChange body) {
    return visits.cancel(ws, id, body);
  }

  @PostMapping("/visits/{id}/confirm")
  public Map<String, Object> confirm(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return visits.confirm(ws, id);
  }

  @PostMapping("/callbacks")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> callback(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.VoiceCallback body) {
    return crm.createCallback(ws, body.leadId(), body.dueAt(), body.reason(),
        body.requestedBy() == null ? "CUSTOMER" : body.requestedBy());
  }

  @PostMapping("/dnc")
  public Map<String, Object> addDnc(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.Dnc body) {
    tenant.require(ws);
    return dnc.add(ws, body.phone(), body.reason(), body.source() == null ? "VOICE_AGENT" : body.source(),
        body.leadId(), tenant.user());
  }

  @GetMapping("/dnc/check")
  public Map<String, Object> checkDnc(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @RequestParam String phone) {
    tenant.require(ws);
    return dnc.check(ws, phone);
  }

  @PatchMapping("/leads/{id}")
  public Map<String, Object> patchLead(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.LeadPatch body) {
    return crm.patchLead(ws, id, body);
  }
}
