package com.estateos.controller;

import com.estateos.service.VoiceCatalogService;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

/**
 * Inventory lookups for the voice agent, answered while a customer is on the line.
 *
 * <p>Separate from the CRM's own resource endpoints because the shapes differ: the agent needs
 * spoken facts (a price range for a configuration), not paginated rows for a table.
 */
@RestController
@RequestMapping("/api/v1/voice")
@Validated
public class VoiceCatalogController {
  private final VoiceCatalogService catalog;

  public VoiceCatalogController(VoiceCatalogService catalog) {
    this.catalog = catalog;
  }

  /** The full speakable catalogue: every project and locality the agent must recognise. */
  @GetMapping("/catalog")
  public Map<String, Object> catalog(@RequestHeader("X-Workspace-Id") @Positive Long ws) {
    return catalog.catalog(ws);
  }

  @GetMapping("/projects/{id}")
  public Map<String, Object> project(
      @RequestHeader("X-Workspace-Id") @Positive Long ws, @PathVariable @Positive Long id) {
    return catalog.project(ws, id);
  }

  /** POST so a caller's free-text locality never lands in a URL access log. */
  @PostMapping("/units/search")
  public Map<String, Object> search(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @RequestBody(required = false) Map<String, Object> body) {
    Map<String, Object> request = body == null ? Map.of() : body;
    BigDecimal budget = decimal(request.get("budgetInr"));
    List<BigDecimal> bhk = new ArrayList<>();
    if (request.get("bhk") instanceof List<?> values)
      for (Object value : values) {
        BigDecimal parsed = decimal(value);
        if (parsed != null) bhk.add(parsed);
      }
    String locality = request.get("locality") == null ? null : request.get("locality").toString();
    int limit = request.get("limit") == null ? 3 : Integer.parseInt(request.get("limit").toString());
    return Map.of("matches", catalog.searchUnits(ws, budget, bhk, locality, limit));
  }

  @GetMapping("/projects/{id}/availability")
  public Map<String, Object> availability(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam(required = false) BigDecimal bhk) {
    return catalog.availability(ws, id, bhk);
  }

  @GetMapping("/projects/{id}/price")
  public Map<String, Object> price(
      @RequestHeader("X-Workspace-Id") @Positive Long ws,
      @PathVariable @Positive Long id,
      @RequestParam BigDecimal bhk) {
    return catalog.price(ws, id, bhk);
  }

  private static BigDecimal decimal(Object value) {
    if (value == null || value.toString().isBlank()) return null;
    try {
      return new BigDecimal(value.toString());
    } catch (NumberFormatException e) {
      throw com.estateos.exception.ApiException.bad("Expected a number, got: " + value);
    }
  }
}
