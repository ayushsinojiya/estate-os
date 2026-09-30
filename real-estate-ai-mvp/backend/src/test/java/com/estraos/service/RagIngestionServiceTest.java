package com.estraos.service;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

import com.estraos.exception.ApiException;
import com.estraos.security.TenantContext;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class RagIngestionServiceTest {
  private static final String ID = "799c7ce2-6723-462c-8e50-06f80275667c";
  private TenantContext tenant;
  private MockRestServiceServer server;
  private RagIngestionService ingestion;
  private RestClient client;

  @BeforeEach
  void setup() {
    tenant = mock(TenantContext.class);
    when(tenant.user()).thenReturn(42L);
    var builder = RestClient.builder().baseUrl("http://ingestion.test");
    server = MockRestServiceServer.bindTo(builder).build();
    client = builder.build();
    ingestion = new RagIngestionService(tenant, client, "private-service-token");
  }

  @Test
  void readsOnlyAuthorizedWorkspaceWithTrustedActorAndCorrectSearchEncoding() {
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources?page=0&size=20&search=A%20%26%20B&status="))
        .andExpect(header("Authorization", "Bearer private-service-token"))
        .andExpect(header("X-Actor-Id", "42"))
        .andRespond(withSuccess("{\"items\":[],\"total\":0}", MediaType.APPLICATION_JSON));
    assertEquals(0, ingestion.list(7L, 0, 20, "A & B", "").get("total").asInt());
    verify(tenant).require(7L);
    server.verify();
  }

  @Test
  void sendsBatchMultipartWithoutChangingSourceIdentity() {
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/batches"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentTypeCompatibleWith(MediaType.MULTIPART_FORM_DATA))
        .andExpect(content().string(org.hamcrest.Matchers.containsString("filename=\"inventory.csv\"")))
        .andExpect(content().string(org.hamcrest.Matchers.containsString("project,bhk")))
        .andRespond(withSuccess("{\"batchId\":\"batch\",\"results\":[{\"id\":\"" + ID + "\",\"status\":\"QUEUED\"}]}", MediaType.APPLICATION_JSON));
    var file = new MockMultipartFile("files", "inventory.csv", "text/csv", "project,bhk".getBytes(StandardCharsets.UTF_8));
    assertEquals(ID, ingestion.upload(7L, List.of(file)).get("results").get(0).get("id").asText());
    verify(tenant).manage(7L);
    server.verify();
  }

  @Test
  void rejectsNonManagersBeforeSendingFilesOrActions() {
    doThrow(ApiException.forbidden()).when(tenant).manage(7L);
    assertEquals(403, assertThrows(ApiException.class, () -> ingestion.retry(7L, ID)).status);
    assertEquals(403, assertThrows(ApiException.class, () -> ingestion.delete(7L, ID)).status);
    assertEquals(403, assertThrows(ApiException.class, () -> ingestion.upload(7L, List.of())).status);
    assertEquals(403, assertThrows(ApiException.class, () -> ingestion.replace(7L, ID, List.of())).status);
    server.verify();
  }

  @Test
  void rejectsCrossWorkspaceReadsAndInvalidSourcePaths() {
    doThrow(ApiException.forbidden()).when(tenant).require(8L);
    assertEquals(403, assertThrows(ApiException.class, () -> ingestion.details(8L, ID)).status);
    assertEquals(400, assertThrows(ApiException.class, () -> ingestion.details(7L, "../sources")).status);
    assertEquals(400, assertThrows(ApiException.class, () -> ingestion.list(7L, -1, 20, "", "")).status);
    server.verify();
  }

  @Test
  void missingTokenFailsClearlyWithoutNetwork() {
    ingestion = new RagIngestionService(tenant, client, " ");
    var error = assertThrows(ApiException.class, () -> ingestion.details(7L, ID));
    assertEquals(503, error.status);
    assertTrue(error.getMessage().contains("RAG_INGESTION_TOKEN"));
    server.verify();
  }

  @Test
  void upstreamAuthFailureDoesNotExpireCrmSessionOrLeakInternalResponse() {
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID))
        .andRespond(withStatus(HttpStatus.UNAUTHORIZED).body("secret internal details"));
    var error = assertThrows(ApiException.class, () -> ingestion.details(7L, ID));
    assertEquals(503, error.status);
    assertFalse(error.getMessage().contains("secret"));
    server.verify();
  }

  @Test
  void forwardsRetryAndDeleteAsQueuedActions() {
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID + "/retry"))
        .andExpect(method(HttpMethod.POST))
        .andRespond(withSuccess("{\"jobId\":\"retry-job\",\"status\":\"QUEUED\"}", MediaType.APPLICATION_JSON));
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID))
        .andExpect(method(HttpMethod.DELETE))
        .andRespond(withSuccess("{\"jobId\":\"delete-job\",\"status\":\"QUEUED\"}", MediaType.APPLICATION_JSON));
    assertEquals("retry-job", ingestion.retry(7L, ID).get("jobId").asText());
    assertEquals("delete-job", ingestion.delete(7L, ID).get("jobId").asText());
    server.verify();
  }

  @Test
  void replacementUsesStableSourceIdAndRequiresExactlyOneFile() {
    assertEquals(400, assertThrows(ApiException.class, () -> ingestion.replace(7L, ID, List.of())).status);
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID + "/replace"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().string(org.hamcrest.Matchers.containsString("filename=\"renamed.csv\"")))
        .andRespond(withSuccess("{\"results\":[]}", MediaType.APPLICATION_JSON));
    ingestion.replace(7L, ID, List.of(new MockMultipartFile("files", "renamed.csv", "text/csv", "name".getBytes(StandardCharsets.UTF_8))));
    server.verify();
  }
}
