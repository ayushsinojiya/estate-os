package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.integration.ExternalServiceException;
import com.estraos.integration.NotificationServiceClient;
import com.estraos.mapper.DtoMapper;
import com.estraos.repository.TenantRepository;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** A small persisted reminder dispatcher. Row locks coordinate multiple API replicas. */
@Service
@ConditionalOnProperty(name = "app.notifications.reminders-enabled", havingValue = "true", matchIfMissing = true)
public class NotificationReminderService {
    private final JdbcTemplate db;
    private final TenantRepository repository;
    private final DtoMapper mapper;
    private final NotificationServiceClient provider;
    private final AuditService audit;

    public NotificationReminderService(JdbcTemplate db, TenantRepository repository, DtoMapper mapper,
                                       NotificationServiceClient provider, AuditService audit) {
        this.db = db;
        this.repository = repository;
        this.mapper = mapper;
        this.provider = provider;
        this.audit = audit;
    }

    @Scheduled(fixedDelayString = "${app.notifications.reminder-poll-ms:60000}", initialDelayString = "${app.notifications.reminder-poll-ms:60000}")
    @Transactional
    public void dispatchDue() {
        List<Map<String, Object>> pending = db.queryForList("""
            SELECT id, workspace_id, user_id, data FROM notifications
            WHERE status = 'SCHEDULED' AND data->>'dueAt' IS NOT NULL
              AND (data->>'dueAt')::timestamptz <= now()
            ORDER BY (data->>'dueAt')::timestamptz, id
            LIMIT 20 FOR UPDATE SKIP LOCKED
            """);
        for (Map<String, Object> row : pending) {
            long id = ((Number) row.get("id")).longValue();
            long workspace = ((Number) row.get("workspace_id")).longValue();
            Long user = row.get("user_id") == null ? null : ((Number) row.get("user_id")).longValue();
            Map<String, Object> data = mapper.read(row.get("data").toString());
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("workspaceId", Long.toString(workspace));
            payload.put("notificationId", Long.toString(id));
            payload.put("requestId", "notification-" + id);
            payload.put("recipientUserId", user == null ? null : user.toString());
            payload.put("recipient", data.get("recipient"));
            payload.put("language", data.getOrDefault("language", "en"));
            payload.put("type", data.get("type"));
            payload.put("message", data.get("message"));
            payload.put("resourceId", data.get("resourceId"));
            Map<String, Object> delivery;
            String state;
            try {
                delivery = provider.send(payload);
                state = String.valueOf(delivery.getOrDefault("status", "QUEUED"));
                // Provider state cannot put the same row back into the scheduler's work queue.
                if (state.equals("SCHEDULED")) state = "QUEUED";
            } catch (ExternalServiceException failure) {
                state = "FAILED";
                delivery = Map.of("status", state, "error", failure.getMessage(), "code", failure.getCode());
                audit.record(workspace, null, "EXTERNAL_SERVICE_FAILED", "NOTIFICATION", id);
            }
            data.put("dispatchedAt", Instant.now().toString());
            data.put("mock", delivery.getOrDefault("mock", false));
            data.put("requestId", "notification-" + id);
            repository.save("notifications", workspace, id, data, Map.of("status", state));
            repository.event("notification_deliveries", workspace, "notification_id", id, delivery);
            repository.save("outbox_events", workspace, null,
                Map.of("notificationId", Long.toString(id), "type", "REMINDER_DISPATCH", "status", state), Map.of());
            audit.record(workspace, null, "REMINDER_DISPATCHED", "NOTIFICATION", id);
        }
    }
}
