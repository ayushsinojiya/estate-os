package com.estraos.integration;

import java.util.Map;
import java.util.UUID;

/** Demo adapter: records what would be sent. No message leaves the system. */
final class MockWhatsAppClient implements WhatsAppClient {
    public boolean configured() { return true; }

    public Map<String, Object> sendTemplate(Map<String, Object> request) {
        IntegrationPayloads.context(request, false);
        IntegrationPayloads.required(request, "to");
        IntegrationPayloads.required(request, "template");
        return Map.of("messageId", "mock-wamid-" + UUID.randomUUID(), "status", "MOCK_DELIVERED", "mock", true,
            "message", "Demo adapter: no WhatsApp message was sent");
    }

    public String uploadMedia(String filename, String contentType, byte[] content) {
        return "mock-media-" + UUID.nameUUIDFromBytes(content);
    }
}
