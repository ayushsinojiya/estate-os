package com.estraos.integration;

import java.util.Map;

/** Boundary to the knowledge service; the application authorizes context before calling. */
public interface RagServiceClient {
    Map<String, Object> searchKnowledgeBase(Map<String, Object> request);
    Map<String, Object> indexPublishedContent(Map<String, Object> request);
    Map<String, Object> reindexDocument(Map<String, Object> request);
    Map<String, Object> getProcessingStatus(Map<String, Object> request);
    Map<String, Object> unpublishContent(Map<String, Object> request);

    /**
     * Uploads one file as a knowledge source. {@code request} carries workspaceId and optional
     * projectId, projectName, locality, crmDocumentId, crmFileId, title, docType and language. The
     * response has the source {@code id} and its {@code status} (UPLOADED, DUPLICATE or REJECTED).
     */
    Map<String, Object> uploadSource(Map<String, Object> request, String filename, String contentType, byte[] content);

    /** Current state of a source: {@code request} carries workspaceId and sourceId. */
    Map<String, Object> getSource(Map<String, Object> request);

    Map<String, Object> deleteSource(Map<String, Object> request);
}
