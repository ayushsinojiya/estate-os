package com.estraos.integration;

import java.util.Map;

/** REST mode without WhatsApp credentials: sends are recorded as failed, nothing else breaks. */
final class DisabledWhatsAppClient implements WhatsAppClient {
    public boolean configured() { return false; }

    private static ExternalServiceException off() {
        return new ExternalServiceException("whatsapp", "WHATSAPP_NOT_CONFIGURED", 503,
            "WhatsApp is not configured (set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN)");
    }

    public Map<String, Object> sendTemplate(Map<String, Object> request) { throw off(); }

    public String uploadMedia(String filename, String contentType, byte[] content) { throw off(); }
}
