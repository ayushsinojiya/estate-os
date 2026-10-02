package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.exception.ApiException;
import com.estraos.repository.TenantRepository;
import com.estraos.security.TenantContext;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/**
 * Stores the actual file behind a property document, for single and bulk uploads, and hands it to
 * the knowledge service, which parses, indexes and publishes it automatically.
 */
@Service
public class DocumentFileService {
  private static final byte[] PDF_MAGIC = "%PDF-".getBytes(StandardCharsets.US_ASCII);
  /** The formats the knowledge service ingests: extension -> stored content type. */
  static final Map<String, String> TYPES =
      Map.ofEntries(
          Map.entry("pdf", "application/pdf"),
          Map.entry(
              "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
          Map.entry(
              "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
          Map.entry("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
          Map.entry("xls", "application/vnd.ms-excel"),
          Map.entry("csv", "text/csv"),
          Map.entry("txt", "text/plain"),
          Map.entry("md", "text/markdown"),
          Map.entry("jpg", "image/jpeg"),
          Map.entry("jpeg", "image/jpeg"),
          Map.entry("png", "image/png"),
          Map.entry("webp", "image/webp"));

  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final TenantContext tenant;
  private final AuditService audit;
  private final KnowledgeService knowledge;
  private final long maxBytes;

  public DocumentFileService(
      NamedParameterJdbcTemplate db,
      TenantRepository repo,
      TenantContext tenant,
      AuditService audit,
      KnowledgeService knowledge,
      @Value("${app.documents.max-file-bytes:52428800}") long maxBytes) {
    this.db = db;
    this.repo = repo;
    this.tenant = tenant;
    this.audit = audit;
    this.knowledge = knowledge;
    this.maxBytes = maxBytes;
  }

  static String extension(String name) {
    int dot = name.lastIndexOf('.');
    return dot < 0 ? "" : name.substring(dot + 1).toLowerCase(Locale.ROOT);
  }

  private static boolean startsWith(byte[] content, byte[] prefix) {
    return content.length >= prefix.length
        && Arrays.equals(Arrays.copyOf(content, prefix.length), prefix);
  }

  /**
   * True when the bytes are what the name says. The declared content type comes from the browser
   * and is trivially spoofed, so the file's own header decides wherever the format has one.
   */
  static boolean matches(String ext, byte[] content) {
    return switch (ext) {
      case "pdf" -> startsWith(content, PDF_MAGIC);
      case "docx", "pptx", "xlsx" -> startsWith(content, new byte[] {'P', 'K'});
      case "xls" -> startsWith(content, new byte[] {(byte) 0xD0, (byte) 0xCF, 0x11, (byte) 0xE0});
      case "png" -> startsWith(content, new byte[] {(byte) 0x89, 'P', 'N', 'G'});
      case "jpg", "jpeg" -> startsWith(content, new byte[] {(byte) 0xFF, (byte) 0xD8});
      case "webp" ->
          content.length > 12
              && startsWith(content, "RIFF".getBytes(StandardCharsets.US_ASCII))
              && new String(content, 8, 4, StandardCharsets.US_ASCII).equals("WEBP");
      case "csv", "txt", "md" -> {
        try {
          StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(content));
          yield true;
        } catch (java.nio.charset.CharacterCodingException e) {
          yield false;
        }
      }
      default -> false;
    };
  }

  /** Accepts the upload only if it is genuinely one of the knowledge formats. */
  private byte[] fileBytes(MultipartFile file, String name) {
    if (file == null || file.isEmpty()) throw ApiException.bad("The uploaded file is empty");
    if (file.getSize() > maxBytes)
      throw ApiException.bad("File exceeds the " + (maxBytes / 1048576) + " MB upload limit");
    String ext = extension(name);
    if (!TYPES.containsKey(ext))
      throw ApiException.bad(
          "Unsupported file type. Upload PDF, Word, PowerPoint, Excel, CSV, text or an image");
    byte[] content;
    try {
      content = file.getBytes();
    } catch (java.io.IOException e) {
      throw ApiException.bad("The upload could not be read");
    }
    if (!matches(ext, content))
      throw ApiException.bad("The file's contents do not match its ." + ext + " extension");
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
    String name = safeName(file.getOriginalFilename());
    byte[] content = fileBytes(file, name);
    Map<String, Object> params = new HashMap<>();
    params.put("ws", ws);
    params.put("doc", documentId);
    params.put("filename", name);
    params.put("type", TYPES.get(extension(name)));
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
    // Indexing is automatic: the knowledge service parses, embeds and publishes the file, and the
    // document's status follows it (see KnowledgeService).
    knowledge.sendDocumentFile(ws, documentId, tenant.user());
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
        byte[] content = fileBytes(file, name);
        int dot = name.lastIndexOf('.');
        String title = dot > 0 ? name.substring(0, dot) : name;
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

  /** The stored file itself, for download. */
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
