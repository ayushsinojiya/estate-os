package com.estraos.controller;

import com.estraos.security.TenantContext;
import com.estraos.service.KnowledgeInventoryImport;
import jakarta.validation.constraints.Positive;
import java.util.List;
import java.util.Map;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

/** Which File management files have been turned into Projects & inventory, and a manual re-sync. */
@RestController
@RequestMapping("/api/v1/knowledge/imports")
@Validated
public class KnowledgeImportController {
  private final KnowledgeInventoryImport importer;
  private final TenantContext tenant;

  public KnowledgeImportController(KnowledgeInventoryImport importer, TenantContext tenant) {
    this.importer = importer;
    this.tenant = tenant;
  }

  @GetMapping
  public Map<String, Object> list(@RequestHeader("X-Workspace-Id") @Positive Long workspace) {
    tenant.require(workspace);
    return Map.of("items", importer.imports(workspace));
  }

  /** Reads every file again now, including ones that failed before. */
  @PostMapping("/sync")
  public Map<String, Object> sync(@RequestHeader("X-Workspace-Id") @Positive Long workspace) {
    tenant.manage(workspace);
    List<Map<String, Object>> items = importer.syncWorkspace(workspace, true);
    return Map.of("items", items);
  }
}
