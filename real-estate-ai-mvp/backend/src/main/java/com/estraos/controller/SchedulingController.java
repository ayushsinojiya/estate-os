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

/** CRM screens for visit slots, project agents, callbacks and the do-not-call list. */
@RestController
@RequestMapping("/api/v1")
@Validated
public class SchedulingController {
  private final VisitSlotService visits;
  private final VoiceCrmService crm;
  private final DncService dnc;
  private final TenantContext tenant;

  public SchedulingController(VisitSlotService visits, VoiceCrmService crm, DncService dnc, TenantContext tenant) {
    this.visits = visits;
    this.crm = crm;
    this.dnc = dnc;
    this.tenant = tenant;
  }

  @GetMapping("/projects/{id}/visit-slots")
  public Map<String, Object> templates(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return visits.templates(ws, id);
  }

  @PutMapping("/projects/{id}/visit-slots")
  public Map<String, Object> saveTemplates(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.SlotTemplates body) {
    return visits.saveTemplates(ws, id, body);
  }

  @GetMapping("/visit-slots/default")
  public Map<String, Object> defaultTemplates(@RequestHeader("X-Workspace-Id") @Positive Long ws) {
    return visits.templates(ws, null);
  }

  @PutMapping("/visit-slots/default")
  public Map<String, Object> saveDefaultTemplates(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.SlotTemplates body) {
    return visits.saveTemplates(ws, null, body);
  }

  @GetMapping("/projects/{id}/slots")
  public Map<String, Object> slots(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam(required = false) LocalDate from,
      @RequestParam(defaultValue = "3") int days) {
    return visits.slots(ws, id, from, days);
  }

  @GetMapping("/projects/{id}/blackouts")
  public List<Map<String, Object>> blackouts(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return visits.blackouts(ws, id);
  }

  @PostMapping("/projects/{id}/blackouts")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> addBlackout(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Blackout body) {
    return visits.addBlackout(ws, id, body);
  }

  @DeleteMapping("/blackouts/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void deleteBlackout(@RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    visits.deleteBlackout(ws, id);
  }

  @GetMapping("/projects/{id}/agents")
  public List<Map<String, Object>> agents(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return visits.projectAgents(ws, id);
  }

  @PutMapping("/projects/{id}/agents")
  public List<Map<String, Object>> saveAgents(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.ProjectAgents body) {
    return visits.saveProjectAgents(ws, id, body);
  }

  @PutMapping("/members/{id}/availability")
  public Map<String, Object> availability(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.MemberAvailability body) {
    return visits.setAvailability(ws, id, body.available());
  }

  @GetMapping("/leads/{id}/callbacks")
  public List<Map<String, Object>> callbacks(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return crm.callbacks(ws, id);
  }

  @PostMapping("/leads/{id}/callbacks")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createCallback(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Callback body) {
    return crm.createCallback(ws, id, body.dueAt(), body.reason(),
        body.requestedBy() == null ? "AGENT" : body.requestedBy());
  }

  @PostMapping("/callbacks/{id}/cancel")
  public Map<String, Object> cancelCallback(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return crm.cancelCallback(ws, id);
  }

  @PostMapping("/dnc")
  public Map<String, Object> addDnc(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.Dnc body) {
    tenant.require(ws);
    return dnc.add(ws, body.phone(), body.reason(), body.source() == null ? "MANUAL" : body.source(),
        body.leadId(), tenant.user());
  }

  @GetMapping("/dnc/check")
  public Map<String, Object> checkDnc(@RequestHeader("X-Workspace-Id") @Positive Long ws, @RequestParam String phone) {
    tenant.require(ws);
    return dnc.check(ws, phone);
  }
}
