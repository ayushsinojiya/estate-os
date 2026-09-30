package com.estraos.integration;

import java.util.LinkedHashMap;
import java.util.Map;

public final class RestVoiceAgentServiceClient implements VoiceAgentServiceClient {
    private final ProviderHttpClient http;
    RestVoiceAgentServiceClient(ProviderHttpClient http) { this.http = http; }

    public Map<String, Object> startOutboundCall(Map<String, Object> request) {
        Map<String, Object> payload = IntegrationPayloads.context(request, false);
        payload.put("leadId", IntegrationPayloads.id(request, "leadId"));
        IntegrationPayloads.required(request, "phone");
        return result(http.post("/v1/calls/outbound", payload), payload);
    }
    public Map<String, Object> getCallDetails(Map<String, Object> request) {
        Map<String, Object> payload = IntegrationPayloads.context(request, false);
        IntegrationPayloads.required(request, "externalId");
        return result(http.post("/v1/calls/details", payload), payload);
    }
    private Map<String, Object> result(Map<String, Object> response, Map<String, Object> request) {
        if (response.get("externalId") == null || response.get("status") == null
            || !request.get("workspaceId").equals(String.valueOf(response.get("workspaceId")))
            || (request.get("leadId") != null && response.get("leadId") != null && !request.get("leadId").toString().equals(response.get("leadId").toString()))
            || (request.get("projectId") != null && response.get("projectId") != null && !request.get("projectId").toString().equals(response.get("projectId").toString()))
            || (request.get("externalId") != null && !request.get("externalId").toString().equals(response.get("externalId").toString())))
            throw IntegrationPayloads.invalidResponse("voice");
        Map<String, Object> result = new LinkedHashMap<>(response);
        for (String key : java.util.List.of("workspaceId", "projectId", "leadId")) {
            if (result.get(key) != null) result.put(key, result.get(key).toString());
        }
        result.put("mock", false);
        return result;
    }
}
