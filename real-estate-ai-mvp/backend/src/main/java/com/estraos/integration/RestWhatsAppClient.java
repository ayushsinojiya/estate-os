package com.estraos.integration;

import java.util.*;

/** POST /{phone-number-id}/messages and /{phone-number-id}/media on graph.facebook.com. */
final class RestWhatsAppClient implements WhatsAppClient {
    private final ProviderHttpClient http;
    private final String phoneNumberId;

    RestWhatsAppClient(ProviderHttpClient http, String phoneNumberId) {
        this.http = http;
        if (phoneNumberId == null || !phoneNumberId.matches("[0-9]{5,30}"))
            throw new IllegalStateException("WHATSAPP_PHONE_NUMBER_ID must be the numeric phone number id");
        this.phoneNumberId = phoneNumberId;
    }

    public boolean configured() { return true; }

    public Map<String, Object> sendTemplate(Map<String, Object> request) {
        IntegrationPayloads.context(request, false);
        String to = IntegrationPayloads.required(request, "to").replaceAll("[^0-9]", "");
        if (to.length() < 10 || to.length() > 15) throw new IllegalArgumentException("WhatsApp recipient must be 10 to 15 digits");
        Map<String, Object> template = new LinkedHashMap<>();
        template.put("name", IntegrationPayloads.required(request, "template"));
        template.put("language", Map.of("code", IntegrationPayloads.required(request, "templateLanguage")));
        template.put("components", request.getOrDefault("components", List.of()));
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("messaging_product", "whatsapp");
        body.put("to", to);
        body.put("type", "template");
        body.put("template", template);
        Map<String, Object> response = http.post("/" + phoneNumberId + "/messages", body);
        if (!(response.get("messages") instanceof List<?> messages) || messages.isEmpty()
            || !(messages.getFirst() instanceof Map<?, ?> first) || first.get("id") == null)
            throw IntegrationPayloads.invalidResponse("whatsapp");
        return Map.of("messageId", first.get("id").toString(), "status", "SENT", "mock", false);
    }

    public String uploadMedia(String filename, String contentType, byte[] content) {
        Map<String, Object> response = http.multipart("/" + phoneNumberId + "/media",
            Map.of("messaging_product", "whatsapp", "type", contentType), "file", filename, contentType, content);
        if (response.get("id") == null) throw IntegrationPayloads.invalidResponse("whatsapp");
        return response.get("id").toString();
    }
}
