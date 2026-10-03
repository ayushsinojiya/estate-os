package com.estraos.integration;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Demo adapter: no document is parsed or indexed. It simulates the knowledge service's
 * automatic publication — an upload is accepted, and the next status check reports it PUBLISHED —
 * so the document lifecycle can be exercised without the service. Search returns nothing rather
 * than inventing brochure facts.
 */
final class MockRagServiceClient implements RagServiceClient {
    public Map<String, Object> searchKnowledgeBase(Map<String, Object> request) {
        IntegrationPayloads.publishedSearch(request);
        return Map.of("results", List.of(), "mock", true, "message", "Demo adapter: no live document retrieval was performed");
    }
    public Map<String, Object> indexPublishedContent(Map<String, Object> request) { return status(request, true, "PUBLISHED"); }
    public Map<String, Object> reindexDocument(Map<String, Object> request) { return status(request, true, "PUBLISHED"); }
    public Map<String, Object> getProcessingStatus(Map<String, Object> request) { return status(request, false, "PUBLISHED"); }
    public Map<String, Object> unpublishContent(Map<String, Object> request) { return status(request, false, "UNPUBLISHED"); }

    public Map<String, Object> uploadSource(Map<String, Object> request, String filename, String contentType, byte[] content) {
        String workspace = IntegrationPayloads.id(request, "workspaceId");
        IntegrationPayloads.uploadFields(request);
        String id = UUID.nameUUIDFromBytes((workspace + ":" + filename + ":" + content.length)
            .getBytes(StandardCharsets.UTF_8)).toString();
        return Map.of("id", id, "status", "UPLOADED", "filename", filename, "mock", true);
    }
    public Map<String, Object> getSource(Map<String, Object> request) {
        String workspace = IntegrationPayloads.id(request, "workspaceId");
        return Map.of("id", IntegrationPayloads.sourceId(request), "workspaceId", workspace, "status", "PUBLISHED",
            "lowConfidencePages", List.of(), "warnings", List.of(), "mock", true);
    }
    public Map<String, Object> deleteSource(Map<String, Object> request) {
        return Map.of("id", IntegrationPayloads.sourceId(request), "status", "DELETED", "mock", true);
    }
    private Map<String, Object> status(Map<String, Object> request, boolean publishing, String status) {
        Map<String, Object> payload = IntegrationPayloads.document(request, publishing);
        return Map.of("documentId", payload.get("documentId"), "status", status, "mock", true,
            "message", "Demo adapter: no external index was changed");
    }
}
