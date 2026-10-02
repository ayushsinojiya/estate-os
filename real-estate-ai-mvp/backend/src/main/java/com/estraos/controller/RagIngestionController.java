package com.estraos.controller;

import com.estraos.service.RagIngestionService;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.Positive;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1/knowledge")
@Validated
public class RagIngestionController {
  private final RagIngestionService ingestion;

  public RagIngestionController(RagIngestionService ingestion) {
    this.ingestion = ingestion;
  }

  @GetMapping("/sources")
  public JsonNode list(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @RequestParam(defaultValue = "0") int page,
      @RequestParam(defaultValue = "20") int size,
      @RequestParam(defaultValue = "") String search,
      @RequestParam(defaultValue = "") String status) {
    return ingestion.list(workspace, page, size, search, status);
  }

  @GetMapping("/sources/{id}")
  public JsonNode details(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @PathVariable String id) {
    return ingestion.details(workspace, id);
  }

  @PostMapping(value = "/batches", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
  @ResponseStatus(HttpStatus.ACCEPTED)
  public JsonNode upload(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @RequestParam("files") List<MultipartFile> files) {
    return ingestion.upload(workspace, files);
  }

  @PostMapping(value = "/sources/{id}/replace", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
  @ResponseStatus(HttpStatus.ACCEPTED)
  public JsonNode replace(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @PathVariable String id, @RequestParam("files") List<MultipartFile> files) {
    return ingestion.replace(workspace, id, files);
  }

  @PostMapping("/sources/{id}/retry")
  @ResponseStatus(HttpStatus.ACCEPTED)
  public JsonNode retry(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @PathVariable String id) {
    return ingestion.retry(workspace, id);
  }

  @PostMapping("/sources/{id}/publish")
  public JsonNode publish(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @PathVariable String id) {
    return ingestion.publish(workspace, id, true);
  }

  @PostMapping("/sources/{id}/unpublish")
  public JsonNode unpublish(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @PathVariable String id) {
    return ingestion.publish(workspace, id, false);
  }

  @DeleteMapping("/sources/{id}")
  @ResponseStatus(HttpStatus.ACCEPTED)
  public JsonNode delete(@RequestHeader("X-Workspace-Id") @Positive Long workspace,
      @PathVariable String id) {
    return ingestion.delete(workspace, id);
  }
}
