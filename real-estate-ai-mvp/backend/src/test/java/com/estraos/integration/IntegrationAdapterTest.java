package com.estraos.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class IntegrationAdapterTest {
    private static final String WORKSPACE = "101";
    private static final String OTHER = "102";
    private static final String PROJECT = "201";
    private static final String DOCUMENT = "301";
    private static final String LEAD = "401";
    private HttpServer server;
    private final AtomicReference<String> path = new AtomicReference<>();
    private final AtomicReference<String> body = new AtomicReference<>();
    private final AtomicReference<String> auth = new AtomicReference<>();
    private final AtomicReference<String> idempotency = new AtomicReference<>();

    @AfterEach void cleanup() { if (server != null) server.stop(0); }

    @Test void ragPropagatesAuthTenantLanguageAndFiltersUnpublishedAndForeignCitations() throws IOException {
        String good = citation(WORKSPACE, PROJECT, DOCUMENT, "PUBLISHED");
        ProviderHttpClient http = server(200, "{\"results\":[" + good + ","
            + citation(OTHER, PROJECT, DOCUMENT, "PUBLISHED") + ","
            + citation(WORKSPACE, PROJECT, DOCUMENT, "DRAFT") + ","
            + citation(WORKSPACE, OTHER, DOCUMENT, "PUBLISHED") + ","
            + citation(WORKSPACE, PROJECT, OTHER, "PUBLISHED") + "],\"answer\":\"unscoped secret\"}", 0, 2000);
        Map<String, Object> request = search();
        request.put("publishedOnly", false);
        request.put("status", "DRAFT");
        Map<String, Object> result = new RestRagServiceClient(http).searchKnowledgeBase(request);
        assertThat(path.get()).isEqualTo("/v1/knowledge/search");
        assertThat(auth.get()).isEqualTo("Bearer test-only-key");
        assertThat(body.get()).contains("\"workspaceId\":\"" + WORKSPACE, "\"language\":\"gu\"", "\"publishedOnly\":true", "\"status\":\"PUBLISHED\"");
        assertThat((List<?>) result.get("results")).hasSize(1);
        assertThat(result).doesNotContainKey("answer").containsEntry("mock", false);
        assertThat(request).containsEntry("publishedOnly", false);
    }

    @Test void allRagDocumentOperationsMapToProvisionalPaths() throws IOException {
        RestRagServiceClient rag = new RestRagServiceClient(server(200, "{\"status\":\"COMPLETED\"}", 0, 2000));
        Map<String, Object> request = document();
        rag.indexPublishedContent(request);
        assertThat(path.get()).isEqualTo("/v1/content/index");
        assertThat(body.get()).contains("\"publishedOnly\":true", "\"projectId\":\"" + PROJECT);
        rag.reindexDocument(request);
        assertThat(path.get()).isEqualTo("/v1/documents/reindex");
        rag.getProcessingStatus(request);
        assertThat(path.get()).isEqualTo("/v1/documents/status");
        rag.unpublishContent(request);
        assertThat(path.get()).isEqualTo("/v1/content/unpublish");
    }

    @Test void invalidOrDraftScopeNeverReachesProvider() throws IOException {
        RestRagServiceClient rag = new RestRagServiceClient(server(200, "{}", 0, 2000));
        Map<String, Object> draft = document();
        draft.put("status", "DRAFT");
        assertThatThrownBy(() -> rag.indexPublishedContent(draft)).isInstanceOf(IllegalArgumentException.class).hasMessageContaining("published");
        assertThatThrownBy(() -> rag.searchKnowledgeBase(Map.of("workspaceId", WORKSPACE))).isInstanceOf(IllegalArgumentException.class).hasMessageContaining("publishedDocumentIds");
        assertThatThrownBy(() -> rag.getProcessingStatus(Map.of("workspaceId", WORKSPACE))).isInstanceOf(IllegalArgumentException.class).hasMessageContaining("projectId");
        assertThat(path.get()).isNull();
    }

    @Test void voiceMapsOutboundAndDetailsAndIdempotencyHeader() throws IOException {
        RestVoiceAgentServiceClient voice = new RestVoiceAgentServiceClient(server(200,
            "{\"externalId\":\"call-1\",\"workspaceId\":\"" + WORKSPACE + "\",\"status\":\"QUEUED\"}", 0, 2000));
        Map<String, Object> request = call();
        request.put("requestId", "request-123");
        assertThat(voice.startOutboundCall(request)).containsEntry("externalId", "call-1").containsEntry("mock", false);
        assertThat(path.get()).isEqualTo("/v1/calls/outbound");
        assertThat(idempotency.get()).isEqualTo("request-123");
        assertThat(body.get()).contains("\"leadId\":\"" + LEAD);
        voice.getCallDetails(Map.of("workspaceId", WORKSPACE, "externalId", "call-1"));
        assertThat(path.get()).isEqualTo("/v1/calls/details");
    }

    @Test void voiceRejectsForeignProviderResponse() throws IOException {
        RestVoiceAgentServiceClient voice = new RestVoiceAgentServiceClient(server(200,
            "{\"externalId\":\"call-1\",\"workspaceId\":\"" + OTHER + "\",\"status\":\"COMPLETED\"}", 0, 2000));
        assertThatThrownBy(() -> voice.startOutboundCall(call())).isInstanceOf(ExternalServiceException.class).hasMessageContaining("invalid response");
    }

    @Test void notificationMapsDeliveryAndDoesNotClaimMock() throws IOException {
        RestNotificationServiceClient notification = new RestNotificationServiceClient(server(202, "{\"status\":\"QUEUED\",\"externalId\":\"delivery-1\"}", 0, 2000));
        assertThat(notification.send(Map.of("workspaceId", WORKSPACE, "type", "SITE_VISIT_CONFIRMATION"))).containsEntry("status", "QUEUED").containsEntry("mock", false);
        assertThat(path.get()).isEqualTo("/v1/notifications");
    }

    @Test void providerErrorsAreSanitized() throws IOException {
        ProviderHttpClient http = server(401, "sensitive-key private-customer provider-diagnostic", 0, 2000);
        assertThatThrownBy(() -> http.post("/v1/test", Map.of())).isInstanceOfSatisfying(ExternalServiceException.class, ex -> {
            assertThat(ex.getCode()).isEqualTo("INTEGRATION_PROVIDER_ERROR");
            assertThat(ex.getStatus()).isEqualTo(502);
            assertThat(ex.getMessage()).doesNotContain("sensitive", "private", "diagnostic", "test-only-key");
            assertThat(ex.getCause()).isNull();
        });
    }

    @Test void readTimeoutIsBoundedAndSanitized() throws IOException {
        ProviderHttpClient http = server(200, "{}", 600, 60);
        assertThatThrownBy(() -> http.post("/v1/test", Map.of())).isInstanceOfSatisfying(ExternalServiceException.class, ex -> {
            assertThat(ex.getCode()).isEqualTo("INTEGRATION_TIMEOUT");
            assertThat(ex.getStatus()).isEqualTo(504);
            assertThat(ex.getCause()).isNull();
        });
    }

    @Test void malformedProviderJsonIsRejected() throws IOException {
        ProviderHttpClient http = server(200, "not json secret", 0, 2000);
        assertThatThrownBy(() -> http.post("/v1/test", Map.of())).isInstanceOf(ExternalServiceException.class).hasMessage("rag service returned an invalid response");
    }

    @Test void productionDefaultsToRestAndFailsClearlyWithoutProviderUrl() {
        IntegrationConfiguration configuration = new IntegrationConfiguration(new MockEnvironment());
        assertThatThrownBy(configuration::ragServiceClient).isInstanceOf(IllegalStateException.class).hasMessageContaining("app.integrations.rag.url");
        for (String invalid : List.of("", "file:///private", "https://user:secret@example.com", "https://example.com/?key=secret", "https://example.com/#key")) {
            assertThatThrownBy(() -> new ProviderHttpClient("voice", invalid, "", 10, 10)).isInstanceOf(IllegalStateException.class).hasMessageNotContaining("secret");
        }
        assertThatThrownBy(() -> new ProviderHttpClient("rag", "https://example.com", "", 0, 10)).isInstanceOf(IllegalStateException.class).hasMessageContaining("timeouts");
    }

    @Test void mocksRequireExplicitModeAndNonProductionProfile() {
        MockEnvironment env = new MockEnvironment().withProperty("app.integrations.mode", "mock");
        assertThatThrownBy(() -> new IntegrationConfiguration(env)).hasMessageContaining("explicit demo or test");
        env.setActiveProfiles("demo", "production");
        assertThatThrownBy(() -> new IntegrationConfiguration(env)).hasMessageContaining("production");
        env.setActiveProfiles("test");
        IntegrationConfiguration configuration = new IntegrationConfiguration(env);
        assertThat(configuration.ragServiceClient().searchKnowledgeBase(search())).containsEntry("mock", true).containsEntry("results", List.of());
        assertThat(configuration.notificationServiceClient().send(Map.of("workspaceId", WORKSPACE))).containsEntry("status", "MOCK_DELIVERED");
        assertThatThrownBy(() -> new IntegrationConfiguration(new MockEnvironment().withProperty("app.integrations.mode", "silent-fallback"))).hasMessageContaining("rest or mock");
    }

    @Test void mockVoiceRemainsScopedAndHasNoOutboundSideEffect() {
        MockVoiceAgentServiceClient voice = new MockVoiceAgentServiceClient();
        Map<String, Object> result = voice.startOutboundCall(call());
        assertThat(result).containsEntry("mock", true).containsEntry("status", "COMPLETED");
        assertThat(result.get("transcript").toString()).contains("no call placed");
        assertThat(voice.getCallDetails(Map.of("workspaceId", WORKSPACE, "externalId", result.get("externalId")))).isEqualTo(result);
        assertThatThrownBy(() -> voice.getCallDetails(Map.of("workspaceId", OTHER, "externalId", result.get("externalId")))).isInstanceOf(ExternalServiceException.class);
    }

    @Test void identitiesRemainExactPositiveLongStrings() {
        assertThat(IntegrationPayloads.context(Map.of("workspaceId", Long.MAX_VALUE, "projectId", 201L), true))
            .containsEntry("workspaceId", "9223372036854775807").containsEntry("projectId", "201");
        for (Object invalid : List.of("0", "-1", "1.5", "9223372036854775808", "10000000-0000-0000-0000-000000000001", "1e2")) {
            assertThatThrownBy(() -> IntegrationPayloads.context(Map.of("workspaceId", invalid), false))
                .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("positive 64-bit integer");
        }
        Map<String, Object> request = IntegrationPayloads.publishedSearch(Map.of("workspaceId", 101L, "publishedDocumentIds", List.of(Long.MAX_VALUE)));
        Map<String, Object> response = IntegrationPayloads.scopeSearchResponse(Map.of("results", List.of(Map.of(
            "workspaceId", 101L, "projectId", 201L, "documentId", Long.MAX_VALUE, "status", "PUBLISHED"))), request);
        Map<?, ?> row = (Map<?, ?>) ((List<?>) response.get("results")).getFirst();
        assertThat(row.get("documentId")).isEqualTo("9223372036854775807");
        assertThat(row.get("workspaceId")).isEqualTo("101");
    }

    private ProviderHttpClient server(int status, String response, long delayMs, int timeoutMs) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            path.set(exchange.getRequestURI().getPath());
            body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            idempotency.set(exchange.getRequestHeaders().getFirst("Idempotency-Key"));
            if (delayMs > 0) {
                try { Thread.sleep(delayMs); } catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
            }
            byte[] bytes = response.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            try {
                exchange.sendResponseHeaders(status, bytes.length);
                exchange.getResponseBody().write(bytes);
            } finally { exchange.close(); }
        });
        server.start();
        return new ProviderHttpClient("rag", "http://127.0.0.1:" + server.getAddress().getPort(), "test-only-key", 1000, timeoutMs);
    }

    private Map<String, Object> search() {
        return new HashMap<>(Map.of("workspaceId", WORKSPACE, "projectId", PROJECT, "language", "gu", "query", "Amenities?", "publishedDocumentIds", List.of(DOCUMENT)));
    }
    private Map<String, Object> document() {
        return new HashMap<>(Map.of("workspaceId", WORKSPACE, "projectId", PROJECT, "documentId", DOCUMENT, "language", "hi", "content", "Published brochure text"));
    }
    private Map<String, Object> call() {
        return new HashMap<>(Map.of("workspaceId", WORKSPACE, "leadId", LEAD, "phone", "+919000000001", "language", "en"));
    }
    private String citation(String workspace, String project, String document, String status) {
        return "{\"workspaceId\":\"" + workspace + "\",\"projectId\":\"" + project + "\",\"documentId\":\"" + document + "\",\"status\":\"" + status + "\",\"text\":\"Scoped brochure content\"}";
    }
}
