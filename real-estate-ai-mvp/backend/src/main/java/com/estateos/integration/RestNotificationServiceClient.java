package com.estateos.integration;

import java.util.LinkedHashMap;
import java.util.Map;

public final class RestNotificationServiceClient implements NotificationServiceClient {
    private final ProviderHttpClient http;
    RestNotificationServiceClient(ProviderHttpClient http) { this.http = http; }

    public Map<String, Object> send(Map<String, Object> request) {
        Map<String, Object> response = http.post("/v1/notifications", IntegrationPayloads.context(request, false));
        if (response.get("status") == null) throw IntegrationPayloads.invalidResponse("notification");
        Map<String, Object> result = new LinkedHashMap<>(response);
        result.put("mock", false);
        return result;
    }
}
