package com.estraos.integration;

import java.util.Map;

/**
 * Meta WhatsApp Cloud API: approved template messages only (no free-form text is ever sent).
 * Callers check the customer's recorded consent before calling.
 */
public interface WhatsAppClient {
    /**
     * {@code request}: workspaceId, to (digits with country code), template, language, components
     * (the Cloud API template components list). Returns messageId, status and mock.
     */
    Map<String, Object> sendTemplate(Map<String, Object> request);

    /** Uploads a document (a brochure PDF) for a template header; returns its media id. */
    String uploadMedia(String filename, String contentType, byte[] content);

    boolean configured();
}
