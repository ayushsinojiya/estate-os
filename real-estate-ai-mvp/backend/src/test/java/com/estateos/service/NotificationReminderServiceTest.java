package com.estateos.service;

import com.estateos.audit.AuditService;
import com.estateos.integration.ExternalServiceException;
import com.estateos.integration.NotificationServiceClient;
import com.estateos.mapper.DtoMapper;
import com.estateos.repository.TenantRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class NotificationReminderServiceTest {
    private final JdbcTemplate db = mock(JdbcTemplate.class);
    private final TenantRepository repository = mock(TenantRepository.class);
    private final NotificationServiceClient provider = mock(NotificationServiceClient.class);
    private final AuditService audit = mock(AuditService.class);
    private final NotificationReminderService service = new NotificationReminderService(db, repository,
        new DtoMapper(new ObjectMapper()), provider, audit);

    private void due() {
        when(db.queryForList(anyString())).thenReturn(List.of(Map.of("id", 31L, "workspace_id", 4L,
            "user_id", 8L, "data", "{\"type\":\"VISIT_REMINDER\",\"message\":\"Visit tomorrow\",\"read\":false}")));
    }

    @Test void dispatchPreservesTenantAndStableIdempotencyAndRecordsDelivery() {
        due();
        when(provider.send(anyMap())).thenReturn(Map.of("status", "MOCK_DELIVERED", "mock", true));
        service.dispatchDue();
        verify(provider).send(argThat(payload -> payload.get("workspaceId").equals("4")
            && payload.get("requestId").equals("notification-31")
            && payload.get("recipientUserId").equals("8")));
        verify(repository).save(eq("notifications"), eq(4L), eq(31L),
            argThat(data -> Boolean.TRUE.equals(data.get("mock")) && data.containsKey("dispatchedAt")), eq(Map.of("status", "MOCK_DELIVERED")));
        verify(repository).event(eq("notification_deliveries"), eq(4L), eq("notification_id"), eq(31L), anyMap());
    }

    @Test void providerFailureIsPersistedWithoutAutomaticRetry() {
        due();
        when(provider.send(anyMap())).thenThrow(new ExternalServiceException("notification", "INTEGRATION_TIMEOUT", 504, "Notification service timed out"));
        service.dispatchDue();
        verify(provider, times(1)).send(anyMap());
        verify(repository).save(eq("notifications"), eq(4L), eq(31L), anyMap(), eq(Map.of("status", "FAILED")));
        verify(audit).record(4L, null, "EXTERNAL_SERVICE_FAILED", "NOTIFICATION", 31L);
    }

    @Test void emptyQueueDoesNotContactProvider() {
        when(db.queryForList(anyString())).thenReturn(List.of());
        service.dispatchDue();
        verifyNoInteractions(provider, repository, audit);
    }
}
