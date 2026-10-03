package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.integration.ExternalServiceException;
import com.estraos.integration.RagServiceClient;
import com.estraos.repository.TenantRepository;
import java.util.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * The CRM's side of the knowledge service: forwards property-document files and applies the
 * processing status it reports back onto the document. (Workspace-wide sources are uploaded on the
 * Files page through the /api/v1/knowledge proxy; general file storage is never sent.)
 *
 * <p>Status flows by polling, not callbacks: the knowledge service holds no credential for this
 * API. {@link #syncPending()} runs on a schedule and the document processing-status endpoint
 * syncs on demand, so a document flips to PUBLISHED within one sync interval of the knowledge
 * service publishing it. Callers authorise the workspace before calling in; nothing here does.
 */
@Service
public class KnowledgeService {
  private static final Logger log = LoggerFactory.getLogger(KnowledgeService.class);
  static final Set<String> IN_FLIGHT = Set.of("QUEUED", "UPLOADED", "PARSING", "EMBEDDING");

  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final RagServiceClient rag;
  private final AuditService audit;

  public KnowledgeService(
      NamedParameterJdbcTemplate db, TenantRepository repo, RagServiceClient rag, AuditService audit) {
    this.db = db;
    this.repo = repo;
    this.rag = rag;
    this.audit = audit;
  }

  private static String text(Object value) {
    return value == null ? null : value.toString();
  }

  // ---------------------------------------------------------------- property documents

  /** Context the knowledge service needs to label chunks: project name, locality, doc type. */
  private Map<String, Object> documentContext(Long ws, Map<String, Object> doc) {
    Long project = EstateService.id(doc.get("projectId"));
    var projectRow = repo.get("projects", ws, project);
    Map<String, Object> request = new LinkedHashMap<>();
    request.put("workspaceId", ws.toString());
    request.put("projectId", project.toString());
    request.put("documentId", text(doc.get("id")));
    request.put("crmDocumentId", text(doc.get("id")));
    request.put("projectName", projectRow.get("name"));
    request.put("locality", projectRow.get("location"));
    request.put("title", doc.get("title"));
    if (doc.get("docType") != null) request.put("docType", doc.get("docType"));
    request.put("language", Objects.requireNonNullElse(doc.get("language"), "en"));
    return request;
  }

  public boolean hasFile(Long ws, Long documentId) {
    Integer n =
        db.queryForObject(
            "SELECT count(*) FROM document_files WHERE workspace_id=:ws AND document_id=:doc",
            Map.of("ws", ws, "doc", documentId),
            Integer.class);
    return n != null && n > 0;
  }

  /**
   * Sends a document's stored file to the knowledge service. A provider failure never undoes the
   * upload: it is recorded on the document as processingStatus FAILED and can be retried by
   * publishing again.
   */
  @Transactional
  public Map<String, Object> sendDocumentFile(Long ws, Long documentId, Long actor) {
    var doc = new LinkedHashMap<>(repo.get("property_documents", ws, documentId));
    var file =
        db.query(
            "SELECT filename, content_type, content FROM document_files WHERE workspace_id=:ws AND"
                + " document_id=:doc",
            Map.of("ws", ws, "doc", documentId),
            (rs, n) ->
                new Object[] {
                  rs.getString("filename"), rs.getString("content_type"), rs.getBytes("content")
                });
    if (file.isEmpty()) return doc;
    try {
      var result =
          rag.uploadSource(
              documentContext(ws, doc),
              (String) file.getFirst()[0],
              (String) file.getFirst()[1],
              (byte[]) file.getFirst()[2]);
      String status = String.valueOf(result.get("status"));
      switch (status) {
        case "REJECTED" -> {
          doc.put("processingStatus", "FAILED");
          doc.put("processingError", result.getOrDefault("reason", "The file was rejected"));
        }
        case "DUPLICATE" -> {
          // The same bytes are already indexed. For this document that is fine; for another
          // document the upload adds nothing new, which the user should know.
          doc.put("ragSourceId", result.get("id"));
          doc.put("processingStatus", result.getOrDefault("existingStatus", "PUBLISHED"));
          doc.put("processingError", "This file is already indexed as another knowledge source");
        }
        default -> {
          doc.put("ragSourceId", result.get("id"));
          doc.put("processingStatus", status);
          doc.put("processingError", null);
        }
      }
      doc.put("mock", result.getOrDefault("mock", false));
    } catch (ExternalServiceException e) {
      doc.put("processingStatus", "FAILED");
      doc.put("processingError", e.getMessage());
      audit.record(ws, actor, "EXTERNAL_SERVICE_FAILED", "DOCUMENT", documentId);
    }
    return repo.save("property_documents", ws, documentId, doc, Map.of());
  }

  /** Asks the knowledge service where a document is and records the answer. */
  @Transactional(noRollbackFor = ExternalServiceException.class)
  public Map<String, Object> syncDocument(Long ws, Long documentId) {
    var doc = new LinkedHashMap<>(repo.get("property_documents", ws, documentId));
    Map<String, Object> request = new LinkedHashMap<>();
    request.put("workspaceId", ws.toString());
    request.put("projectId", text(doc.get("projectId")));
    request.put("documentId", documentId.toString());
    request.put("language", Objects.requireNonNullElse(doc.get("language"), "en"));
    var result = rag.getProcessingStatus(request);
    apply(ws, documentId, doc, result);
    return result;
  }

  /** The knowledge service is the authority on whether a document is searchable. */
  void apply(Long ws, Long documentId, Map<String, Object> doc, Map<String, Object> status) {
    String processing = String.valueOf(status.getOrDefault("status", "UNKNOWN"));
    doc.put("processingStatus", processing);
    doc.put("processingError", status.get("error"));
    for (String key :
        List.of("lowConfidencePages", "warnings", "chunkCount", "pageCount", "sourceId", "docType"))
      if (status.get(key) != null) doc.put(key.equals("sourceId") ? "ragSourceId" : key, status.get(key));
    doc.put("processingCheckedAt", java.time.Instant.now().toString());
    String column = String.valueOf(doc.get("status"));
    if (processing.equals("PUBLISHED")) column = "PUBLISHED";
    else if (Set.of("UNPUBLISHED", "NOT_INDEXED", "DELETED").contains(processing)) column = "DRAFT";
    doc.put("status", column);
    repo.save("property_documents", ws, documentId, doc, Map.of("status", column));
  }

  // ---------------------------------------------------------------- scheduled sync

  /**
   * Sends a document whose text was written before the knowledge service could be reached (the
   * demo seed, or a publish while it was down). Retried on every sync until it is accepted.
   */
  @Transactional(noRollbackFor = ExternalServiceException.class)
  public void indexPending(Long ws, Long documentId) {
    var doc = new LinkedHashMap<>(repo.get("property_documents", ws, documentId));
    var request = documentContext(ws, doc);
    request.put("content", doc.get("content"));
    request.put("projectLocation", request.get("locality"));
    request.put("status", "PUBLISHED");
    request.put("publishedOnly", true);
    var result = rag.indexPublishedContent(request);
    doc.put("processingStatus", result.getOrDefault("status", "QUEUED"));
    doc.put("mock", result.getOrDefault("mock", false));
    repo.save("property_documents", ws, documentId, doc, Map.of());
  }

  /** One pass over everything still being processed. Row locks keep replicas from overlapping. */
  @Transactional
  public int syncPending() {
    int synced = 0;
    var queued =
        db.getJdbcTemplate()
            .queryForList(
                "SELECT workspace_id, id FROM property_documents WHERE data->>'processingStatus'="
                    + "'PENDING_INDEX' AND status='PUBLISHED' ORDER BY id LIMIT 20 FOR UPDATE SKIP LOCKED");
    for (var row : queued) {
      try {
        indexPending(((Number) row.get("workspace_id")).longValue(), ((Number) row.get("id")).longValue());
        synced++;
      } catch (ExternalServiceException e) {
        log.info("Knowledge service not reachable yet for document {}: {}", row.get("id"), e.getMessage());
      }
    }
    var documents =
        db.getJdbcTemplate()
            .queryForList(
                "SELECT workspace_id, id FROM property_documents WHERE data->>'processingStatus' IN"
                    + " ('QUEUED','UPLOADED','PARSING','EMBEDDING') ORDER BY updated_at LIMIT 50 FOR"
                    + " UPDATE SKIP LOCKED");
    for (var row : documents) {
      Long ws = ((Number) row.get("workspace_id")).longValue();
      Long id = ((Number) row.get("id")).longValue();
      try {
        syncDocument(ws, id);
        synced++;
      } catch (ExternalServiceException e) {
        log.warn("Knowledge status for document {} unavailable: {}", id, e.getMessage());
      }
    }
    return synced;
  }
}
