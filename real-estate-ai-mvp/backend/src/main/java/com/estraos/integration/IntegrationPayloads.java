package com.estraos.integration;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class IntegrationPayloads {
    private static final Set<String> LANGUAGES = Set.of("en", "hi", "gu", "mr");
    private IntegrationPayloads() { }

    static Map<String, Object> context(Map<String, Object> request, boolean projectRequired) {
        if (request == null) throw new IllegalArgumentException("Integration request is required");
        Map<String, Object> result = new LinkedHashMap<>(request);
        result.put("workspaceId", id(request, "workspaceId"));
        if (projectRequired || request.get("projectId") != null) result.put("projectId", id(request, "projectId"));
        for (String key : List.of("leadId", "documentId", "resourceId", "entityId", "recipientId", "recipientUserId", "notificationId", "agentId", "unitId", "appointmentId")) {
            if (request.get(key) != null) result.put(key, id(request, key));
        }
        String language = String.valueOf(request.getOrDefault("language", "en")).toLowerCase(java.util.Locale.ROOT);
        if (!LANGUAGES.contains(language)) throw new IllegalArgumentException("Unsupported integration language");
        result.put("language", language);
        return result;
    }

    static Map<String, Object> document(Map<String, Object> request, boolean publishing) {
        Map<String, Object> result = context(request, true);
        if (result.get("documentId") == null && result.get("resourceId") != null) result.put("documentId", result.get("resourceId"));
        result.put("documentId", id(result, "documentId"));
        if (publishing) {
            if (request.containsKey("status") && !"PUBLISHED".equals(request.get("status")))
                throw new IllegalArgumentException("Only published content may be indexed");
            result.put("status", "PUBLISHED");
            result.put("publishedOnly", true);
        }
        return result;
    }

    static String required(Map<String, Object> request, String key) {
        Object value = request.get(key);
        if (value == null || value.toString().isBlank()) throw new IllegalArgumentException(key + " is required for integration");
        return value.toString();
    }

    static String id(Map<String, Object> request, String key) {
        String value = required(request, key);
        try {
            if (!value.matches("[0-9]{1,19}") || Long.parseLong(value) < 1) throw new IllegalArgumentException();
            return Long.toString(Long.parseLong(value));
        } catch (IllegalArgumentException ex) { throw new IllegalArgumentException(key + " must be a positive 64-bit integer"); }
    }

    /** Upload metadata: workspace plus optional, validated identity fields. Values are strings. */
    static Map<String, String> uploadFields(Map<String, Object> request) {
        Map<String, Object> context = context(request, false);
        Map<String, String> fields = new LinkedHashMap<>();
        for (String key : List.of("projectId", "crmDocumentId", "crmFileId")) {
            if (request.get(key) != null) fields.put(key, id(request, key));
        }
        for (String key : List.of("projectName", "locality", "title", "docType")) {
            Object value = request.get(key);
            if (value != null && !value.toString().isBlank()) fields.put(key, value.toString().strip());
        }
        if (request.get("language") != null) fields.put("language", context.get("language").toString());
        return fields;
    }

    static String sourceId(Map<String, Object> request) {
        String value = required(request, "sourceId");
        try {
            return java.util.UUID.fromString(value).toString();
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("sourceId must be a UUID");
        }
    }

    static Map<String, Object> publishedSearch(Map<String, Object> request) {
        Map<String, Object> result = context(request, false);
        result.put("publishedOnly", true);
        result.put("status", "PUBLISHED");
        Object ids = request.get("publishedDocumentIds");
        if (!(ids instanceof List<?> list)) throw new IllegalArgumentException("publishedDocumentIds is required for retrieval");
        result.put("publishedDocumentIds", list.stream().map(value -> id(java.util.Collections.singletonMap("documentId", value), "documentId")).toList());
        return result;
    }

    static Map<String, Object> scopeSearchResponse(Map<String, Object> response, Map<String, Object> request) {
        Object raw = response.get("results");
        if (!(raw instanceof List<?> rows)) throw invalidResponse("rag");
        List<?> allowed = (List<?>) request.get("publishedDocumentIds");
        List<?> filtered = rows.stream().filter(value -> {
            if (!(value instanceof Map<?, ?> row)) return false;
            return String.valueOf(request.get("workspaceId")).equals(String.valueOf(row.get("workspaceId")))
                && (request.get("projectId") == null || String.valueOf(request.get("projectId")).equals(String.valueOf(row.get("projectId"))))
                && "PUBLISHED".equals(row.get("status"))
                && allowed.contains(String.valueOf(row.get("documentId")));
        }).map(value -> {
            Map<String, Object> row = new LinkedHashMap<>();
            ((Map<?, ?>) value).forEach((key, field) -> row.put(key.toString(), field));
            for (String key : List.of("workspaceId", "projectId", "documentId")) {
                if (row.get(key) != null) row.put(key, row.get(key).toString());
            }
            return row;
        }).toList();
        // Do not relay provider-generated top-level answers, which may include unscoped facts.
        return Map.of("results", filtered, "mock", false);
    }

    static ExternalServiceException invalidResponse(String service) {
        return new ExternalServiceException(service, "INTEGRATION_INVALID_RESPONSE", 502, service + " service returned an invalid response");
    }
}
