package com.estraos.audit;

import com.estraos.repository.TenantRepository;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class AuditService {
  private final TenantRepository repo;

  public AuditService(TenantRepository repo) {
    this.repo = repo;
  }

  public void record(Long ws, Long user, String action, String type, Long id) {
    Map<String, Object> cols = new LinkedHashMap<>();
    cols.put("user_id", user);
    cols.put("action", action);
    cols.put("entity_type", type);
    cols.put("entity_id", id);
    repo.save(
        "audit_logs",
        ws,
        null,
        Map.of("description", action.replace('_', ' ').toLowerCase(Locale.ROOT)),
        cols);
  }
}
