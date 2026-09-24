package com.estateos.service;

import com.estateos.audit.AuditService;
import com.estateos.exception.ApiException;
import com.estateos.repository.TenantRepository;
import com.estateos.security.TenantContext;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/** Stores the actual PDF behind a property document, for single and bulk uploads. */
@Service
public class DocumentFileService {
  private static final byte[] PDF_MAGIC = "%PDF-".getBytes(StandardCharsets.US_ASCII);

  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final TenantContext tenant;
  private final AuditService audit;
  private final long maxBytes;

  public DocumentFileService(
      NamedParameterJdbcTemplate db,
      TenantRepository repo,
      TenantContext tenant,
      AuditService audit,
      @Value("${app.documents.max-file-bytes:20971520}") long maxBytes) {
    this.db = db;
    this.repo = repo;
    this.tenant = tenant;
    this.audit = audit;
    this.maxBytes = maxBytes;
  }

  /**
   * Accepts the upload only if it is genuinely a PDF.
   *
   * <p>The declared content type comes from the browser and is trivially spoofed, so the file's own
   * header decides. Anything else is rejected before a byte reaches the database.
   */
  private byte[] pdfBytes(MultipartFile file) {
    if (file == null || file.isEmpty()) throw ApiException.bad("The uploaded file is empty");
    if (file.getSize() > maxBytes)
      throw ApiException.bad("File exceeds the " + (maxBytes / 1048576) + " MB upload limit");
    byte[] content;
    try {
      content = file.getBytes();
    } catch (java.io.IOException e) {
      throw ApiException.bad("The upload could not be read");
    }
    if (content.length < PDF_MAGIC.length
        || !Arrays.equals(Arrays.copyOf(content, PDF_MAGIC.length), PDF_MAGIC))
      throw ApiException.bad("Only PDF files can be uploaded");
    return content;
  }

  /** Strips any directory component a browser may send, keeping a readable name. */
  static String safeName(String original) {
    String name = original == null ? "" : original;
    int cut = Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\'));
    name = cut >= 0 ? name.substring(cut + 1) : name;
    name = name.replaceAll("[\\p{Cntrl}]", "").trim();
    if (name.length() > 255) name = name.substring(name.length() - 255);
    return name.isBlank() ? "document.pdf" : name;
  }

  private static String sha256(byte[] content) {
    try {
      var digest = MessageDigest.getInstance("SHA-256").digest(content);
      StringBuilder out = new StringBuilder(64);
      for (byte b : digest) out.append(String.format("%02x", b));
      return out.toString();
    } catch (Exception e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }

  /** Attaches (or replaces) the file for one existing document. */
  @Transactional
  public Map<String, Object> store(Long ws, Long documentId, MultipartFile file) {
    tenant.manage(ws);
    repo.get("property_documents", ws, documentId); // authorises the document in this workspace
    byte[] content = pdfBytes(file);
    String name = safeName(file.getOriginalFilename());
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("doc", documentId);
    params.put("filename", name);
    params.put("type", "application/pdf");
    params.put("size", (long) content.length);
    params.put("sha", sha256(content));
    params.put("content", content);
    db.update(
        "INSERT INTO document_files(workspace_id,document_id,filename,content_type,size_bytes,"
            + "sha256,content) VALUES (:ws,:doc,:filename,:type,:size,:sha,:content)"
            + " ON CONFLICT (workspace_id,document_id) DO UPDATE SET filename=excluded.filename,"
            + " content_type=excluded.content_type, size_bytes=excluded.size_bytes,"
            + " sha256=excluded.sha256, content=excluded.content, updated_at=now()",
        params);
    audit.record(ws, tenant.user(), "DOCUMENT_FILE_UPLOADED", "PROPERTY_DOCUMENT", documentId);
    return describe(ws, documentId);
  }

  /**
   * Bulk drag-and-drop: one document record is created per file, then the file is attached.
   *
   * <p>Each file is handled independently so one bad file in a dropped folder does not discard the
   * rest; the response reports per-file outcomes.
   */
  @Transactional
  public Map<String, Object> bulkUpload(Long ws, Long projectId, List<MultipartFile> files) {
    tenant.manage(ws);
    repo.get("projects", ws, projectId);
    if (files == null || files.isEmpty()) throw ApiException.bad("No files were uploaded");
    if (files.size() > 50) throw ApiException.bad("Upload at most 50 files at a time");

    List<Map<String, Object>> uploaded = new ArrayList<>();
    List<Map<String, Object>> rejected = new ArrayList<>();
    for (MultipartFile file : files) {
      String name = safeName(file.getOriginalFilename());
      try {
        byte[] content = pdfBytes(file);
        String title = name.toLowerCase(Locale.ROOT).endsWith(".pdf")
            ? name.substring(0, name.length() - 4)
            : name;
        var saved =
            repo.save(
                "property_documents",
                ws,
                null,
                EstateService.fields(
                    "sourceFilename", name,
                    "sizeBytes", content.length,
                    "uploadedViaBulk", true),
                EstateService.fields(
                    "project_id", projectId,
                    "title", title.length() > 200 ? title.substring(0, 200) : title,
                    "status", "DRAFT"));
        Long documentId = EstateService.id(saved.get("id"));
        store(ws, documentId, file);
        uploaded.add(Map.of("documentId", documentId.toString(), "filename", name,
            "sizeBytes", content.length));
      } catch (ApiException e) {
        rejected.add(Map.of("filename", name, "reason", e.getMessage()));
      }
    }
    if (uploaded.isEmpty() && !rejected.isEmpty())
      throw ApiException.bad("No file could be uploaded: " + rejected.getFirst().get("reason"));
    audit.record(ws, tenant.user(), "DOCUMENTS_BULK_UPLOADED", "PROJECT", projectId);
    return Map.of("uploaded", uploaded, "rejected", rejected,
        "uploadedCount", uploaded.size(), "rejectedCount", rejected.size());
  }

  /** File metadata for one document, or null when nothing has been uploaded. */
  public Map<String, Object> describe(Long ws, Long documentId) {
    tenant.require(ws);
    var rows =
        db.query(
            "SELECT filename, content_type, size_bytes, sha256, updated_at FROM document_files"
                + " WHERE workspace_id=:ws AND document_id=:doc",
            Map.of("ws", ws, "doc", documentId),
            (rs, n) -> {
              Map<String, Object> row = new LinkedHashMap<>();
              row.put("documentId", documentId.toString());
              row.put("filename", rs.getString("filename"));
              row.put("contentType", rs.getString("content_type"));
              row.put("sizeBytes", rs.getLong("size_bytes"));
              row.put("sha256", rs.getString("sha256"));
              row.put("uploadedAt", rs.getTimestamp("updated_at").toInstant().toString());
              return row;
            });
    return rows.isEmpty() ? Map.of("documentId", documentId.toString(), "file", false)
        : rows.getFirst();
  }

  public record StoredFile(String filename, String contentType, byte[] content) {}

  /** The stored PDF itself, for download. */
  public StoredFile download(Long ws, Long documentId) {
    tenant.require(ws);
    var rows =
        db.query(
            "SELECT filename, content_type, content FROM document_files"
                + " WHERE workspace_id=:ws AND document_id=:doc",
            Map.of("ws", ws, "doc", documentId),
            (rs, n) ->
                new StoredFile(
                    rs.getString("filename"), rs.getString("content_type"), rs.getBytes("content")));
    if (rows.isEmpty()) throw ApiException.missing();
    return rows.getFirst();
  }
}
