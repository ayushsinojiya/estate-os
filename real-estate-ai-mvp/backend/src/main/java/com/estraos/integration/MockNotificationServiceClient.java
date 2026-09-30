package com.estraos.integration;

import java.util.Map;

final class MockNotificationServiceClient implements NotificationServiceClient {
    public Map<String, Object> send(Map<String, Object> request) {
        IntegrationPayloads.context(request, false);
        return Map.of("status", "MOCK_DELIVERED", "mock", true, "message", "Demo notification recorded; no message sent");
    }
}
