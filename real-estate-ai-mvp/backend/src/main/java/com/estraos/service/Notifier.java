package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.integration.ExternalServiceException;
import com.estraos.integration.NotificationServiceClient;
import com.estraos.repository.TenantRepository;
import java.util.*;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

/** In-app notifications to workspace users, delivered through the notification gateway. */
@Service
public class Notifier {
  private final TenantRepository repo;
  private final NotificationServiceClient notification;
  private final AuditService audit;
  private final NamedParameterJdbcTemplate db;

  public Notifier(TenantRepository repo, NotificationServiceClient notification, AuditService audit,
                  NamedParameterJdbcTemplate db) {
    this.repo = repo;
    this.notification = notification;
    this.audit = audit;
    this.db = db;
  }

  /** Records and dispatches one notification. Returns the delivery state; never throws on delivery. */
  public String notify(Long ws, Long user, String type, String message, Long resource) {
    Map<String, Object> data = EstateService.fields(
        "type", type, "title", type.replace('_', ' '), "message", message, "resourceId", resource, "read", false);
    var saved = repo.save("notifications", ws, null, data, EstateService.fields("user_id", user, "status", "PENDING"));
    Long uuid = EstateService.id(saved.get("id"));
    Map<String, Object> payload = EstateService.fields(
        "workspaceId", ws.toString(), "notificationId", uuid.toString(),
        "recipientUserId", user == null ? null : user.toString(), "type", type, "message", message);
    String state;
    Map<String, Object> delivery;
    try {
      delivery = notification.send(payload);
      state = delivery.getOrDefault("status", "PENDING").toString();
    } catch (ExternalServiceException e) {
      state = "FAILED";
      delivery = EstateService.fields("status", state, "error", e.getMessage());
      audit.record(ws, null, "EXTERNAL_SERVICE_FAILED", "NOTIFICATION", uuid);
    }
    data.put("mock", delivery.getOrDefault("mock", false));
    repo.save("notifications", ws, uuid, data, EstateService.fields("status", state));
    repo.event("notification_deliveries", ws, "notification_id", uuid, delivery);
    repo.save("outbox_events", ws, null,
        EstateService.fields("type", type, "notificationId", uuid, "status", state), Map.of());
    return state;
  }

  /** Every ADMIN and MANAGER of the workspace, e.g. for a visit that needs reassignment. */
  public void managers(Long ws, String type, String message, Long resource) {
    var users = db.queryForList(
        "SELECT m.user_id FROM workspace_members m JOIN roles r ON r.id=m.role_id JOIN users u ON"
            + " u.id=m.user_id WHERE m.workspace_id=:ws AND r.name IN ('ADMIN','MANAGER') AND u.enabled"
            + " AND u.email NOT LIKE 'voice-agent%'",
        Map.of("ws", ws), Long.class);
    for (Long user : users) notify(ws, user, type, message, resource);
  }
}
