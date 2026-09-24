package com.estateos.integration;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

final class MockVoiceAgentServiceClient implements VoiceAgentServiceClient {
    private final Map<String, Map<String, Object>> calls = new ConcurrentHashMap<>();

    public Map<String, Object> startOutboundCall(Map<String, Object> request) {
        Map<String, Object> context = IntegrationPayloads.context(request, false);
        String leadId = IntegrationPayloads.id(request, "leadId");
        IntegrationPayloads.required(request, "phone");
        String workspaceId = context.get("workspaceId").toString();
        String externalId = "demo-" + UUID.nameUUIDFromBytes((workspaceId + ":" + leadId + ":"
            + request.getOrDefault("requestId", "preview")).getBytes(StandardCharsets.UTF_8));
        Map<String, Object> result = Map.of("externalId", externalId, "workspaceId", workspaceId, "leadId", leadId,
            "status", "COMPLETED", "outcome", "QUALIFIED", "mock", true,
            "summary", "Demo conversation: customer is exploring a two-bedroom home and requested an agent follow-up.",
            "transcript", "[DEMO — no call placed]\nAssistant: What are you looking for?\nCustomer: A two-bedroom home. Please ask an agent to contact me.\nAssistant: Your assigned agent can confirm live availability and arrange a visit.",
            "requirements", Map.of("bhk", 2, "intent", "BUY", "language", context.get("language"), "notes", "Demo fixture; confirm all requirements with the customer"));
        calls.put(workspaceId + ":" + externalId, result);
        return result;
    }

    public Map<String, Object> getCallDetails(Map<String, Object> request) {
        Map<String, Object> context = IntegrationPayloads.context(request, false);
        String externalId = IntegrationPayloads.required(request, "externalId");
        Map<String, Object> result = calls.get(context.get("workspaceId") + ":" + externalId);
        if (result == null) throw new ExternalServiceException("voice", "INTEGRATION_CALL_NOT_FOUND", 502,
            "Demo call is unavailable; start a demo call in this application session");
        return result;
    }
}
