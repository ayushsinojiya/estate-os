package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.exception.ApiException;
import com.estraos.repository.TenantRepository;
import com.estraos.security.TenantContext;
import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/**
 * Workspace-isolated filesystem storage with retained, auditable history. Files in a format the
 * knowledge service understands are also sent there as workspace-wide knowledge.
 */
@Service
public class ManagedFileService {
  static final long MAX_BYTES = 50L * 1024 * 1024;
  private static final Set<String> EXTENSIONS = Set.of(
      "pdf", "doc", "docx", "txt", "md", "xls", "xlsx", "csv", "ppt", "pptx",
      "jpg", "jpeg", "png", "webp", "zip");
  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final TenantContext tenant;
  private final AuditService audit;
  private final KnowledgeService knowledge;
  private final Path root;

  public ManagedFileService(NamedParameterJdbcTemplate db, TenantRepository repo, TenantContext tenant,
      AuditService audit, KnowledgeService knowledge,
      @Value("${app.files.storage-path:./storage/files}") String storagePath) {
    this.db = db; this.repo = repo; this.tenant = tenant; this.audit = audit; this.knowledge = knowledge;
    this.root = Paths.get(storagePath).toAbsolutePath().normalize();
  }

  static String safeName(String original) {
    String name = original == null ? "" : original.replace('\\', '/');
    name = name.substring(name.lastIndexOf('/') + 1).replaceAll("[\\p{Cntrl}]", "").trim();
    if (name.length() > 255) name = name.substring(name.length() - 255);
    return name.isBlank() ? "upload" : name;
  }

  static boolean isSupported(String name) {
    int dot = name.lastIndexOf('.');
    return dot > 0 && EXTENSIONS.contains(name.substring(dot + 1).toLowerCase(Locale.ROOT));
  }

  private static String extension(String name) {
    return name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
  }

  private static String checksum(byte[] bytes) {
    try {
      byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
      StringBuilder value = new StringBuilder(64);
      for (byte b : digest) value.append(String.format("%02x", b));
      return value.toString();
    } catch (Exception e) { throw new IllegalStateException("SHA-256 is unavailable", e); }
  }

  private static String message(Exception e) {
    String value = e.getMessage() == null ? "Storage failed" : e.getMessage();
    return value.length() > 500 ? value.substring(0, 500) : value;
  }

  @Transactional
  public Map<String, Object> upload(Long ws, List<MultipartFile> files) {
    tenant.manage(ws);
    if (files == null || files.isEmpty()) throw ApiException.bad("Select at least one file to upload");
    if (files.size() > 50) throw ApiException.bad("Upload at most 50 files at a time");
    repo.workspaceLock(ws); // serializes the active checksum check within this workspace
    List<Map<String, Object>> results = new ArrayList<>();
    for (MultipartFile file : files) results.add(uploadOne(ws, file));
    return Map.of("results", results);
  }

  private Map<String, Object> uploadOne(Long ws, MultipartFile file) {
    String name = safeName(file == null ? null : file.getOriginalFilename());
    if (file == null || file.isEmpty()) return result(name, "FAILED", "The uploaded file is empty", null);
    if (file.getSize() > MAX_BYTES) return result(name, "FAILED", "File exceeds the 50 MB upload limit", null);
    if (!isSupported(name)) return result(name, "FAILED", "This file type is not supported", null);
    byte[] bytes;
    try { bytes = file.getBytes(); } catch (IOException e) { return result(name, "FAILED", "The upload could not be read", null); }
    String sha = checksum(bytes);
    Integer duplicate = db.queryForObject("SELECT count(*) FROM managed_files WHERE workspace_id=:ws AND sha256_checksum=:sha AND status='STORED'",
        Map.of("ws", ws, "sha", sha), Integer.class);
    if (duplicate != null && duplicate > 0) return result(name, "DUPLICATE", "This file has already been uploaded.", null);
    Long id = db.queryForObject("INSERT INTO managed_files(workspace_id,original_file_name,file_extension,mime_type,file_size_bytes,sha256_checksum,status,created_by) VALUES (:ws,:name,:extension,:type,:size,:sha,'UPLOADING',:user) RETURNING id",
        Map.of("ws", ws, "name", name, "extension", extension(name), "type", Optional.ofNullable(file.getContentType()).orElse("application/octet-stream"), "size", (long) bytes.length, "sha", sha, "user", tenant.user()), Long.class);
    String storedName = UUID.randomUUID() + "." + extension(name);
    Path destination = root.resolve("workspace-" + ws).resolve(id.toString()).resolve(storedName).normalize();
    Path temporary = null;
    try {
      if (!destination.startsWith(root)) throw new IOException("Unsafe storage path");
      Files.createDirectories(destination.getParent());
      temporary = Files.createTempFile(destination.getParent(), "upload-", ".tmp");
      Files.write(temporary, bytes, StandardOpenOption.TRUNCATE_EXISTING);
      try {
        Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
      } catch (AtomicMoveNotSupportedException ignored) {
        Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
      }
      String key = root.relativize(destination).toString().replace('\\', '/');
      db.update("UPDATE managed_files SET stored_file_name=:stored, storage_key=:key, status='STORED', updated_at=now() WHERE workspace_id=:ws AND id=:id",
          Map.of("stored", storedName, "key", key, "ws", ws, "id", id));
      audit.record(ws, tenant.user(), "FILE_UPLOADED", "MANAGED_FILE", id);
      String ext = extension(name);
      if (DocumentFileService.TYPES.containsKey(ext) && DocumentFileService.matches(ext, bytes))
        knowledge.sendManagedFile(ws, id, name, DocumentFileService.TYPES.get(ext), bytes, tenant.user());
      return result(name, "STORED", null, id);
    } catch (Exception e) {
      try { Files.deleteIfExists(destination); } catch (IOException ignored) { }
      try { if (temporary != null) Files.deleteIfExists(temporary); } catch (IOException ignored) { }
      db.update("UPDATE managed_files SET status='FAILED', failure_reason=:reason, updated_at=now() WHERE workspace_id=:ws AND id=:id",
          Map.of("reason", message(e), "ws", ws, "id", id));
      return result(name, "FAILED", "The file could not be stored. Please try again.", id);
    }
  }

  public Map<String, Object> list(Long ws, int page, int size, String search, String status) {
    tenant.require(ws);
    int safePage = Math.max(page, 0), safeSize = Math.min(Math.max(size, 1), 100);
    String where = "workspace_id=:ws" + (status == null || status.isBlank() ? "" : " AND status=:status")
        + (search == null || search.isBlank() ? "" : " AND original_file_name ILIKE :search");
    Map<String, Object> params = new HashMap<>(); params.put("ws", ws); params.put("limit", safeSize); params.put("offset", safePage * safeSize);
    if (status != null && !status.isBlank()) params.put("status", status);
    if (search != null && !search.isBlank()) params.put("search", "%" + search.replace("%", "\\%").replace("_", "\\_") + "%" );
    long total = db.queryForObject("SELECT count(*) FROM managed_files WHERE " + where, params, Long.class);
    List<Map<String, Object>> items = db.query("SELECT id,original_file_name,file_extension,mime_type,file_size_bytes,sha256_checksum,status,failure_reason,created_at,updated_at,deleted_at,created_by,knowledge_source_id,knowledge_status,knowledge_error FROM managed_files WHERE " + where + " ORDER BY created_at DESC LIMIT :limit OFFSET :offset", params,
        (rs, n) -> { Map<String,Object> row = new LinkedHashMap<>(); row.put("id", Long.toString(rs.getLong("id"))); row.put("originalFileName", rs.getString("original_file_name")); row.put("fileExtension", rs.getString("file_extension")); row.put("mimeType", rs.getString("mime_type")); row.put("fileSizeBytes", rs.getLong("file_size_bytes")); row.put("sha256Checksum", rs.getString("sha256_checksum")); row.put("status", rs.getString("status")); row.put("failureReason", rs.getString("failure_reason")); row.put("createdAt", rs.getTimestamp("created_at").toInstant().toString()); Timestamp deleted = rs.getTimestamp("deleted_at"); row.put("deletedAt", deleted == null ? null : deleted.toInstant().toString()); row.put("knowledgeSourceId", rs.getString("knowledge_source_id")); row.put("knowledgeStatus", rs.getString("knowledge_status")); row.put("knowledgeError", rs.getString("knowledge_error")); return row; });
    return Map.of("items", items, "total", total, "page", safePage, "size", safeSize);
  }

  @Transactional
  public void delete(Long ws, Long id) {
    tenant.manage(ws);
    var records = db.query("SELECT storage_key,status,knowledge_source_id FROM managed_files WHERE workspace_id=:ws AND id=:id", Map.of("ws", ws, "id", id), (rs,n) -> Map.of("key", Optional.ofNullable(rs.getString("storage_key")).orElse(""), "status", rs.getString("status"), "source", Optional.ofNullable(rs.getString("knowledge_source_id")).orElse("")));
    if (records.isEmpty()) throw ApiException.missing();
    if ("DELETED".equals(records.getFirst().get("status"))) return;
    String key = (String) records.getFirst().get("key");
    try {
      Path target = root.resolve(key).normalize();
      if (!target.startsWith(root)) throw ApiException.bad("The stored file could not be deleted");
      if (!key.isBlank()) Files.deleteIfExists(target);
    } catch (IOException e) { throw ApiException.bad("The stored file could not be deleted"); }
    db.update("UPDATE managed_files SET status='DELETED', deleted_at=now(), updated_at=now(), knowledge_status=CASE WHEN knowledge_source_id IS NULL THEN knowledge_status ELSE 'DELETED' END WHERE workspace_id=:ws AND id=:id", Map.of("ws",ws,"id",id));
    String source = (String) records.getFirst().get("source");
    if (!source.isBlank()) knowledge.deleteManagedFile(ws, UUID.fromString(source), tenant.user(), id);
    audit.record(ws, tenant.user(), "FILE_DELETED", "MANAGED_FILE", id);
  }

  private static Map<String,Object> result(String name, String status, String reason, Long id) {
    Map<String,Object> value = new LinkedHashMap<>(); value.put("filename", name); value.put("status", status); value.put("reason", reason); if (id != null) value.put("id", id.toString()); return value;
  }
}
