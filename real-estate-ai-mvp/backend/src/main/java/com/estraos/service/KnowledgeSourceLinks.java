package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.exception.ApiException;
import com.estraos.repository.TenantRepository;
import com.estraos.security.TenantContext;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/**
 * Keeps a project document in step when its knowledge source is changed from File management.
 *
 * <p>A file uploaded to a project is both a CRM document (what WhatsApp sends as the brochure, what
 * the Projects page shows) and a knowledge source (what the voice agent answers from). File
 * management acts on the source; without this the document would keep the old file after a swap,
 * and stay "published" — and sendable — after a delete.
 */
@Component
public class KnowledgeSourceLinks {
  private final TenantRepository repo;
  private final TenantContext tenant;
  private final AuditService audit;
  private final DocumentFileService files;

  public KnowledgeSourceLinks(
      TenantRepository repo, TenantContext tenant, AuditService audit, DocumentFileService files) {
    this.repo = repo;
    this.tenant = tenant;
    this.audit = audit;
    this.files = files;
  }

  void validate(MultipartFile file) {
    files.validate(file);
  }

  /** The replacement is now the document's file; the status sync follows it to PUBLISHED. */
  @Transactional
  public void replaced(Long ws, Long documentId, MultipartFile file, String processingStatus) {
    var doc = document(ws, documentId);
    if (doc == null) return;
    files.write(ws, documentId, file);
    doc.put("processingStatus", processingStatus == null ? "UPLOADED" : processingStatus);
    doc.put("processingError", null);
    doc.put("sourceReplacedAt", Instant.now().toString());
    repo.save("property_documents", ws, documentId, doc, Map.of());
  }

  /** The source is gone: the document can no longer be answered from, sent, or shown as live. */
  @Transactional
  public void deleted(Long ws, Long documentId) {
    var doc = document(ws, documentId);
    if (doc == null) return;
    files.removeFile(ws, documentId);
    doc.put("status", "DRAFT");
    doc.put("processingStatus", "DELETED");
    doc.put("processingError", null);
    doc.remove("ragSourceId");
    doc.put("sourceDeletedAt", Instant.now().toString());
    repo.save("property_documents", ws, documentId, doc, Map.of("status", "DRAFT"));
    audit.record(ws, tenant.user(), "KNOWLEDGE_SOURCE_DELETED", "PROPERTY_DOCUMENT", documentId);
  }

  /** Publish or unpublish from File management. */
  @Transactional
  public void published(Long ws, Long documentId, boolean published, String processingStatus) {
    var doc = document(ws, documentId);
    if (doc == null) return;
    String status = published ? "PUBLISHED" : "DRAFT";
    doc.put("status", status);
    doc.put("processingStatus", processingStatus);
    repo.save("property_documents", ws, documentId, doc, Map.of("status", status));
  }

  private Map<String, Object> document(Long ws, Long documentId) {
    try {
      return new LinkedHashMap<>(repo.get("property_documents", ws, documentId));
    } catch (ApiException missing) {
      return null; // the CRM document was removed; nothing to keep in step
    }
  }
}
