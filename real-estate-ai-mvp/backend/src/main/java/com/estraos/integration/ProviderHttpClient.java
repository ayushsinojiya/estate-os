package com.estraos.integration;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.Map;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

final class ProviderHttpClient {
    private final String service;
    private final RestClient client;
    private static final ParameterizedTypeReference<Map<String, Object>> MAP = new ParameterizedTypeReference<>() { };

    ProviderHttpClient(String service, String url, String apiKey, int connectTimeoutMs, int readTimeoutMs) {
        this.service = service;
        validateUrl(service, url);
        if (connectTimeoutMs < 1 || readTimeoutMs < 1 || connectTimeoutMs > 120000 || readTimeoutMs > 120000)
            throw new IllegalStateException("Integration timeouts must be between 1 and 120000 milliseconds");
        if (apiKey != null && (apiKey.contains("\r") || apiKey.contains("\n"))) throw new IllegalStateException(service + " API key is invalid");
        // HTTP/1.1: the default HTTP/2 sends an h2c upgrade on plain http, which uvicorn (the knowledge
        // service and the voice agent) rejects as an invalid request.
        HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofMillis(connectTimeoutMs))
            .followRedirects(HttpClient.Redirect.NEVER).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(Duration.ofMillis(readTimeoutMs));
        RestClient.Builder builder = RestClient.builder().baseUrl(url.replaceAll("/+$", ""))
            .requestFactory(factory).defaultHeader("Accept", "application/json");
        if (apiKey != null && !apiKey.isBlank()) builder.defaultHeader("Authorization", "Bearer " + apiKey);
        this.client = builder.build();
    }

    Map<String, Object> post(String path, Map<String, Object> payload) {
        return call(() -> {
            RestClient.RequestBodySpec request = client.post().uri(path).contentType(MediaType.APPLICATION_JSON);
            if (payload.get("requestId") != null) request.header("Idempotency-Key", safeRequestId(payload.get("requestId")));
            return request.body(payload).retrieve();
        });
    }

    Map<String, Object> get(String path) {
        return call(() -> client.get().uri(path).retrieve());
    }

    Map<String, Object> delete(String path) {
        return call(() -> client.delete().uri(path).retrieve());
    }

    /** One file plus plain form fields, as multipart/form-data, in the part named "files". */
    Map<String, Object> multipart(String path, Map<String, String> fields, String filename, String contentType,
                                  byte[] content) {
        return multipart(path, fields, "files", filename, contentType, content);
    }

    Map<String, Object> multipart(String path, Map<String, String> fields, String part, String filename,
                                  String contentType, byte[] content) {
        var parts = new org.springframework.util.LinkedMultiValueMap<String, Object>();
        fields.forEach((key, value) -> { if (value != null) parts.add(key, value); });
        var headers = new org.springframework.http.HttpHeaders();
        headers.setContentType(MediaType.parseMediaType(contentType));
        headers.setContentDispositionFormData(part, filename);
        parts.add(part, new org.springframework.http.HttpEntity<>(content, headers));
        return call(() -> client.post().uri(path).contentType(MediaType.MULTIPART_FORM_DATA).body(parts).retrieve());
    }

    private Map<String, Object> call(java.util.function.Supplier<RestClient.ResponseSpec> send) {
        try {
            Map<String, Object> result = send.get()
                .onStatus(status -> !status.is2xxSuccessful(), (req, response) -> {
                    throw new ExternalServiceException(service, "INTEGRATION_PROVIDER_ERROR", 502, service + " service rejected the request");
                }).body(MAP);
            if (result == null) throw IntegrationPayloads.invalidResponse(service);
            return result;
        } catch (ExternalServiceException ex) { throw ex;
        } catch (ResourceAccessException ex) {
            Throwable cause = ex;
            while (cause != null && !(cause instanceof HttpTimeoutException) && !(cause instanceof java.net.SocketTimeoutException)) cause = cause.getCause();
            boolean timeout = cause != null;
            throw new ExternalServiceException(service, timeout ? "INTEGRATION_TIMEOUT" : "INTEGRATION_UNAVAILABLE", timeout ? 504 : 502,
                service + (timeout ? " service timed out" : " service is unavailable"));
        } catch (RestClientException ex) { throw IntegrationPayloads.invalidResponse(service); }
    }

    private String safeRequestId(Object value) {
        String id = value.toString();
        if (!id.matches("[a-zA-Z0-9_-]{1,128}")) throw new IllegalArgumentException("Invalid integration requestId");
        return id;
    }

    private static void validateUrl(String service, String url) {
        try {
            URI uri = URI.create(url == null ? "" : url);
            if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null)
                throw new IllegalArgumentException();
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException("Configure app.integrations." + service + ".url with an absolute HTTP(S) service URL (no credentials, query or fragment)");
        }
    }
}
