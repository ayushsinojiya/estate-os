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
  void forwardsDateRangeToKnowledgeService() {
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources?page=0&size=20&search=&status=&dateFrom=2020-01-05T00:00:00Z&dateTo=2020-01-06T00:00:00Z"))
        .andRespond(withSuccess("{\"items\":[],\"total\":0}", MediaType.APPLICATION_JSON));
    assertEquals(0, ingestion.list(7L, 0, 20, "", "", "2020-01-05T00:00:00Z", "2020-01-06T00:00:00Z").get("total").asInt());
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
    assertTrue(error.getMessage().contains("RAG_SERVICE_TOKEN"));
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

  // ---- a source that belongs to a project document is kept in step with it

  private static final String LINKED = "{\"id\":\"" + ID + "\",\"crmDocumentId\":\"55\",\"status\":\"PUBLISHED\"}";
  private static final String STANDALONE = "{\"id\":\"" + ID + "\",\"crmDocumentId\":null,\"status\":\"PUBLISHED\"}";

  private KnowledgeSourceLinks linked() {
    var links = mock(KnowledgeSourceLinks.class);
    ingestion = new RagIngestionService(tenant, client, "private-service-token", links);
    return links;
  }

  private void expectDetails(String body) {
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(body, MediaType.APPLICATION_JSON));
  }

  @Test
  void deletingAProjectDocumentsSourceAlsoRetiresTheDocument() {
    var links = linked();
    expectDetails(LINKED);
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID))
        .andExpect(method(HttpMethod.DELETE))
        .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON)
            .body("{\"id\":\"" + ID + "\",\"status\":\"DELETED\"}"));
    assertEquals("DELETED", ingestion.delete(7L, ID).get("status").asText());
    verify(links).deleted(7L, 55L);
    server.verify();
  }

  @Test
  void deletingAWorkspaceSourceTouchesNoDocument() {
    var links = linked();
    expectDetails(STANDALONE);
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID))
        .andExpect(method(HttpMethod.DELETE))
        .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON).body("{}"));
    ingestion.delete(7L, ID);
    verifyNoInteractions(links);
    server.verify();
  }

  @Test
  void swappingAProjectDocumentsSourceStoresTheNewFileOnTheDocument() {
    var links = linked();
    var file = new MockMultipartFile("files", "brochure.pdf", "application/pdf", "%PDF-1.7 v2".getBytes(StandardCharsets.UTF_8));
    expectDetails(LINKED);
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID + "/replace"))
        .andExpect(method(HttpMethod.POST))
        .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON)
            .body("{\"results\":[{\"id\":\"" + ID + "\",\"status\":\"UPLOADED\",\"version\":2}]}"));
    ingestion.replace(7L, ID, List.of(file));
    var order = inOrder(links);
    order.verify(links).validate(file); // checked before the knowledge service is touched
    order.verify(links).replaced(7L, 55L, file, "UPLOADED");
    server.verify();
  }

  @Test
  void aRejectedSwapLeavesTheDocumentAlone() {
    var links = linked();
    var file = new MockMultipartFile("files", "brochure.pdf", "application/pdf", "%PDF-1.7".getBytes(StandardCharsets.UTF_8));
    expectDetails(LINKED);
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID + "/replace"))
        .andRespond(withStatus(HttpStatus.CONFLICT));
    assertEquals(409, assertThrows(ApiException.class, () -> ingestion.replace(7L, ID, List.of(file))).status);
    verify(links, never()).replaced(any(), any(), any(), any());
    server.verify();
  }

  @Test
  void unpublishingFromFileManagementUnpublishesTheDocument() {
    var links = linked();
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID + "/unpublish"))
        .andRespond(withSuccess(LINKED.replace("PUBLISHED", "UNPUBLISHED"), MediaType.APPLICATION_JSON));
    ingestion.publish(7L, ID, false);
    verify(links).published(7L, 55L, false, "UNPUBLISHED");
    server.verify();
  }

  @Test
  void aFailedDocumentUpdateDoesNotUndoTheDelete() {
    var links = linked();
    doThrow(new IllegalStateException("db down")).when(links).deleted(7L, 55L);
    expectDetails(LINKED);
    server.expect(requestTo("http://ingestion.test/v1/workspaces/7/sources/" + ID))
        .andExpect(method(HttpMethod.DELETE))
        .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON).body("{\"status\":\"DELETED\"}"));
    assertEquals("DELETED", ingestion.delete(7L, ID).get("status").asText());
    server.verify();
  }
}
