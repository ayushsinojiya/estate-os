package com.estateos.controller;

import com.estateos.dto.*;
import com.estateos.security.TenantContext;
import com.estateos.service.*;
import jakarta.validation.Valid;
import com.estateos.service.DocumentFileService;
import jakarta.validation.constraints.Positive;
import org.springframework.web.multipart.MultipartFile;
import java.util.*;
import org.springframework.http.*;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
@Validated
public class ApiController {
  private final EstateService service;
  private final AuthService auth;
  private final TenantContext tenant;
  private final DocumentFileService files;
  private final ManagedFileService managedFiles;

  public ApiController(
      EstateService service, AuthService auth, TenantContext tenant, DocumentFileService files,
      ManagedFileService managedFiles) {
    this.service = service;
    this.auth = auth;
    this.tenant = tenant;
    this.files = files;
    this.managedFiles = managedFiles;
  }

  @PostMapping("/auth/login")
  public Map<String, Object> login(@Valid @RequestBody Requests.Login body) {
    return auth.login(body);
  }

  @GetMapping("/auth/me")
  public Map<String, Object> me() {
    return auth.me();
  }

  @PostMapping("/auth/logout")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void logout() {
    auth.logout();
  }

  @GetMapping("/workspaces")
  public List<Map<String, Object>> workspaces() {
    return auth.workspaces(tenant.user());
  }

  @GetMapping("/members")
  public List<Map<String, Object>> members(@RequestHeader("X-Workspace-Id") @Positive Long ws) {
    return auth.members(ws);
  }

  @GetMapping("/dashboard")
  public Map<String, Object> dashboard(@RequestHeader("X-Workspace-Id") @Positive Long ws) {
    return service.dashboard(ws);
  }

  @GetMapping("/projects")
  public PageResponse<?> projects(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("projects", ws, filters);
  }

  @GetMapping("/projects/{id}")
  public Map<String, Object> project(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.get("projects", ws, id);
  }

  @PostMapping("/projects")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createProject(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @Valid @RequestBody Requests.Project body) {
    return service.saveProject(ws, null, body);
  }

  @PutMapping("/projects/{id}")
  public Map<String, Object> updateProject(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Project body) {
    return service.saveProject(ws, id, body);
  }

  @GetMapping("/projects/{id}/buildings")
  public List<?> buildings(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.related("buildings", ws, "project_id", id, "projects");
  }

  @PostMapping("/projects/{id}/buildings")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> building(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Building body) {
    return service.saveBuilding(ws, id, body, "buildings");
  }

  @GetMapping("/projects/{id}/floors")
  public List<?> floors(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.related("floors", ws, "project_id", id, "projects");
  }

  @PostMapping("/projects/{id}/floors")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> floor(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Floor body) {
    return service.saveFloor(ws, id, body);
  }

  @GetMapping("/projects/{id}/unit-types")
  public List<?> types(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.related("unit_types", ws, "project_id", id, "projects");
  }

  @PostMapping("/projects/{id}/unit-types")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> type(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Building body) {
    return service.saveBuilding(ws, id, body, "unit_types");
  }

  @GetMapping("/projects/{id}/units")
  public PageResponse<?> projectUnits(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam Map<String, String> filters) {
    service.get("projects", ws, id);
    filters.put("projectId", id.toString());
    return service.list("units", ws, filters);
  }

  @GetMapping("/projects/{id}/documents")
  public PageResponse<?> projectDocuments(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam Map<String, String> filters) {
    service.get("projects", ws, id);
    filters.put("projectId", id.toString());
    return service.list("property_documents", ws, filters);
  }

  @GetMapping("/amenities")
  public PageResponse<?> amenities(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("amenities", ws, filters);
  }

  @PostMapping("/amenities")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> amenity(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @Valid @RequestBody Requests.Building body) {
    return service.saveAmenity(ws, body);
  }

  @GetMapping("/units")
  public PageResponse<?> units(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("units", ws, filters);
  }

  @GetMapping("/units/{id}")
  public Map<String, Object> unit(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.get("units", ws, id);
  }

  @PostMapping("/units")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createUnit(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.Unit body) {
    return service.saveUnit(ws, null, body);
  }

  @PutMapping("/units/{id}")
  public Map<String, Object> updateUnit(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Unit body) {
    return service.saveUnit(ws, id, body);
  }

  @GetMapping("/units/{id}/history")
  public List<?> unitHistory(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.related("unit_status_history", ws, "unit_id", id, "units");
  }

  @GetMapping("/leads")
  public PageResponse<?> leads(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("leads", ws, filters);
  }

  @GetMapping("/leads/{id}")
  public Map<String, Object> lead(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.get("leads", ws, id);
  }

  @PostMapping("/leads")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createLead(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.Lead body) {
    return service.saveLead(ws, null, body);
  }

  @PutMapping("/leads/{id}")
  public Map<String, Object> updateLead(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Lead body) {
    return service.saveLead(ws, id, body);
  }

  @GetMapping("/leads/{id}/activities")
  public List<?> leadActivities(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.related("lead_activities", ws, "lead_id", id, "leads");
  }

  @PostMapping("/leads/{id}/notes")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> leadNote(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Note body) {
    return service.note(ws, id, body);
  }

  @PostMapping("/leads/{id}/recommendations")
  public List<?> saveRecommendations(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Suggestions body) {
    return service.saveSuggestions(ws, id, body);
  }

  @PostMapping("/recommendations/search")
  public Map<String, Object> recommendations(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @Valid @RequestBody Requests.Recommendation body) {
    return service.recommend(ws, body);
  }

  @GetMapping("/documents")
  public PageResponse<?> documents(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("property_documents", ws, filters);
  }

  @GetMapping("/files")
  public Map<String, Object> files(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam(defaultValue = "0") int page,
      @RequestParam(defaultValue = "10") int size,
      @RequestParam(defaultValue = "") String search,
      @RequestParam(defaultValue = "") String status) {
    return managedFiles.list(ws, page, size, search, status);
  }

  @PostMapping(value = "/files", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> uploadFiles(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam("files") List<MultipartFile> uploads) {
    return managedFiles.upload(ws, uploads);
  }

  @DeleteMapping("/files/{id}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void deleteFile(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    managedFiles.delete(ws, id);
  }

  @GetMapping("/documents/{id}")
  public Map<String, Object> document(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.get("property_documents", ws, id);
  }

  @PostMapping("/documents")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createDocument(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @Valid @RequestBody Requests.Document body) {
    return service.document(ws, body);
  }

  @PutMapping("/documents/{id}/content")
  public Map<String, Object> content(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Content body) {
    return service.content(ws, id, body);
  }

  /** Attach the actual PDF to an already-registered document, or replace the current one. */
  @PostMapping("/documents/{id}/file")
  public Map<String, Object> uploadDocumentFile(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam("file") MultipartFile file) {
    return files.store(ws, id, file);
  }

  @GetMapping("/documents/{id}/file")
  public ResponseEntity<byte[]> downloadDocumentFile(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    var stored = files.download(ws, id);
    return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_TYPE, stored.contentType())
        // attachment, and never inline: a PDF rendered in-origin can script against this app.
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.attachment().filename(stored.filename()).build().toString())
        .header("X-Content-Type-Options", "nosniff")
        .body(stored.content());
  }

  @GetMapping("/documents/{id}/file/info")
  public Map<String, Object> documentFileInfo(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return files.describe(ws, id);
  }

  /** Bulk drag-and-drop: creates one draft document per PDF and stores each file. */
  @PostMapping("/projects/{id}/documents/upload")
  public Map<String, Object> bulkUploadDocuments(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam("files") List<MultipartFile> uploads) {
    return files.bulkUpload(ws, id, uploads);
  }

  @PostMapping("/documents/{id}/publish")
  public Map<String, Object> publish(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.documentAction(ws, id, "publish");
  }

  @PostMapping("/documents/{id}/unpublish")
  public Map<String, Object> unpublish(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.documentAction(ws, id, "unpublish");
  }

  @PostMapping("/documents/{id}/reindex")
  public Map<String, Object> reindex(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.documentAction(ws, id, "reindex");
  }

  @GetMapping("/documents/{id}/versions")
  public List<?> versions(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.related(
        "property_content_versions", ws, "document_id", id, "property_documents");
  }

  @GetMapping("/documents/{id}/processing-status")
  public Map<String, Object> processing(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.processing(ws, id);
  }

  @GetMapping("/calls")
  public PageResponse<?> calls(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("voice_sessions", ws, filters);
  }

  @GetMapping("/calls/{id}")
  public Map<String, Object> call(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.get("voice_sessions", ws, id);
  }

  @PostMapping("/calls")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> startCall(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestHeader(value = "Idempotency-Key", required = false) String key,
      @Valid @RequestBody Requests.Call body) {
    return service.call(ws, body, key);
  }

  /** Voice agent: resolve a caller's number to a lead, creating one on first contact. */
  @PostMapping("/leads/find-or-create")
  public Map<String, Object> findOrCreateLead(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @Valid @RequestBody Requests.LeadLookup body) {
    return service.findOrCreateLead(ws, body);
  }

  /** Voice agent: deliver the post-call record. Idempotent on the agent's session identifier. */
  @PostMapping("/calls/ingest")
  public Map<String, Object> ingestCall(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestHeader(value = "Idempotency-Key", required = false) String key,
      @Valid @RequestBody Requests.CallIngest body) {
    return service.ingestCall(ws, body, key);
  }

  @PostMapping("/calls/{id}/refresh")
  public Map<String, Object> refresh(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.refreshCall(ws, id);
  }

  @GetMapping("/site-visits")
  public PageResponse<?> visits(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("appointments", ws, filters);
  }

  @GetMapping("/site-visits/{id}")
  public Map<String, Object> visit(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.get("appointments", ws, id);
  }

  @PostMapping("/site-visits")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createVisit(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @Valid @RequestBody Requests.Visit body) {
    return service.visit(ws, null, body);
  }

  @PutMapping("/site-visits/{id}")
  public Map<String, Object> updateVisit(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Visit body) {
    return service.visit(ws, id, body);
  }

  @GetMapping("/handovers")
  public PageResponse<?> handovers(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("handover_records", ws, filters);
  }

  @GetMapping("/handovers/{id}")
  public Map<String, Object> handover(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.get("handover_records", ws, id);
  }

  @PostMapping("/handovers")
  @ResponseStatus(HttpStatus.CREATED)
  public Map<String, Object> createHandover(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @Valid @RequestBody Requests.Handover body) {
    return service.handover(ws, null, body);
  }

  @PutMapping("/handovers/{id}")
  public Map<String, Object> updateHandover(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @Valid @RequestBody Requests.Handover body) {
    return service.handover(ws, id, body);
  }

  @GetMapping("/notifications")
  public PageResponse<?> notifications(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("notifications", ws, filters);
  }

  @PostMapping("/notifications/{id}/read")
  public Map<String, Object> read(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return service.readNotification(ws, id);
  }

  @GetMapping("/audit-logs")
  public PageResponse<?> audits(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestParam Map<String, String> filters) {
    return service.list("audit_logs", ws, filters);
  }
}
