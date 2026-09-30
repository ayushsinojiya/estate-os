package com.estraos.integration;

import java.util.Map;

/** Boundary to the existing RAG service; application authorizes context before calling. */
public interface RagServiceClient {
    Map<String, Object> searchKnowledgeBase(Map<String, Object> request);
    Map<String, Object> indexPublishedContent(Map<String, Object> request);
    Map<String, Object> reindexDocument(Map<String, Object> request);
    Map<String, Object> getProcessingStatus(Map<String, Object> request);
    Map<String, Object> unpublishContent(Map<String, Object> request);
}
