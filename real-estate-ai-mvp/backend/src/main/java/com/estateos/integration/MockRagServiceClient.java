package com.estateos.integration;

import java.util.List;
import java.util.Map;

/** Demonstrates transport behavior only; does not implement or simulate semantic retrieval. */
final class MockRagServiceClient implements RagServiceClient {
    public Map<String, Object> searchKnowledgeBase(Map<String, Object> request) {
        IntegrationPayloads.publishedSearch(request);
        return Map.of("results", List.of(), "mock", true, "message", "Demo adapter: no live document retrieval was performed");
    }
    public Map<String, Object> indexPublishedContent(Map<String, Object> request) { return status(request, true, "COMPLETED"); }
    public Map<String, Object> reindexDocument(Map<String, Object> request) { return status(request, true, "COMPLETED"); }
    public Map<String, Object> getProcessingStatus(Map<String, Object> request) { return status(request, false, "COMPLETED"); }
    public Map<String, Object> unpublishContent(Map<String, Object> request) { return status(request, false, "UNPUBLISHED"); }
    private Map<String, Object> status(Map<String, Object> request, boolean publishing, String status) {
        Map<String, Object> payload = IntegrationPayloads.document(request, publishing);
        return Map.of("documentId", payload.get("documentId"), "status", status, "mock", true,
            "message", "Demo adapter: no external index was changed");
    }
}
