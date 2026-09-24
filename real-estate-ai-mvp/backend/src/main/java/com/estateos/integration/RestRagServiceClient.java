package com.estateos.integration;

import java.util.Map;
import java.util.LinkedHashMap;

public final class RestRagServiceClient implements RagServiceClient {
    private final ProviderHttpClient http;
    RestRagServiceClient(ProviderHttpClient http) { this.http = http; }

    public Map<String, Object> searchKnowledgeBase(Map<String, Object> request) {
        Map<String, Object> payload = IntegrationPayloads.publishedSearch(request);
        return IntegrationPayloads.scopeSearchResponse(http.post("/v1/knowledge/search", payload), payload);
    }
    public Map<String, Object> indexPublishedContent(Map<String, Object> request) {
        return status("/v1/content/index", IntegrationPayloads.document(request, true));
    }
    public Map<String, Object> reindexDocument(Map<String, Object> request) {
        return status("/v1/documents/reindex", IntegrationPayloads.document(request, true));
    }
    public Map<String, Object> getProcessingStatus(Map<String, Object> request) {
        return status("/v1/documents/status", IntegrationPayloads.document(request, false));
    }
    public Map<String, Object> unpublishContent(Map<String, Object> request) {
        return status("/v1/content/unpublish", IntegrationPayloads.document(request, false));
    }
    private Map<String, Object> status(String path, Map<String, Object> payload) {
        Map<String, Object> response = http.post(path, payload);
        if (response.get("status") == null
            || (response.get("documentId") != null && !payload.get("documentId").equals(response.get("documentId").toString()))
            || (response.get("workspaceId") != null && !payload.get("workspaceId").equals(response.get("workspaceId").toString())))
            throw IntegrationPayloads.invalidResponse("rag");
        Map<String, Object> result = new LinkedHashMap<>(response);
        for (String key : java.util.List.of("workspaceId", "projectId", "documentId")) {
            if (result.get(key) != null) result.put(key, result.get(key).toString());
        }
        result.put("mock", false);
        return result;
    }
}
