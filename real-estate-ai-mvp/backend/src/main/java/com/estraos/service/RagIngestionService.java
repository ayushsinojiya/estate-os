package com.estraos.service;

import com.estraos.exception.ApiException;
import com.estraos.security.TenantContext;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * Authenticated proxy to the knowledge service's source management (/api/v1/knowledge/*). The
 * Python service owns source storage and ingestion state; this API checks workspace membership and
 * role first, then forwards with the shared RAG_SERVICE_TOKEN.
 */
@Service
public class RagIngestionService {
  private final TenantContext tenant;
  private final RestClient client;
  private final String token;

  @Autowired
  public RagIngestionService(
      TenantContext tenant,
      @Value("${app.integrations.rag.url:}") String url,
      @Value("${app.integrations.rag.api-key:}") String token,
      @Value("${app.integrations.connect-timeout-ms:3000}") int connectTimeout,
      @Value("${app.knowledge.upload-timeout-ms:60000}") int readTimeout) {
    this(tenant, buildClient(url.isBlank() ? "http://localhost:8090" : url, connectTimeout, readTimeout),
        url.isBlank() ? "" : token);
  }

  RagIngestionService(TenantContext tenant, RestClient client, String token) {
    this.tenant = tenant;
    this.client = client;
    this.token = token;
  }

  private static RestClient buildClient(String url, int connectTimeout, int readTimeout) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(connectTimeout));
    factory.setReadTimeout(Duration.ofMillis(readTimeout));
    return RestClient.builder().baseUrl(url).requestFactory(factory).build();
  }

  public JsonNode list(Long workspace, int page, int size, String search, String status) {
    tenant.require(workspace);
    if (page < 0 || size < 1 || size > 100) throw ApiException.bad("Invalid pagination");
    if (search.length() > 200 || status.length() > 30)
      throw ApiException.bad("Search or status is too long");
    var path = UriComponentsBuilder.fromPath(root(workspace) + "/sources")
        .queryParam("page", page).queryParam("size", size)
        .queryParam("search", search).queryParam("status", status)
        .build().encode().toUriString();
    return request(HttpMethod.GET, path, null);
  }

  public JsonNode details(Long workspace, String id) {
    tenant.require(workspace);
    return request(HttpMethod.GET, source(workspace, id), null);
  }

  public JsonNode upload(Long workspace, List<MultipartFile> files) {
    tenant.manage(workspace);
    return request(HttpMethod.POST, root(workspace) + "/batches", parts(files));
  }

  public JsonNode replace(Long workspace, String id, List<MultipartFile> files) {
    tenant.manage(workspace);
    if (files == null || files.size() != 1)
      throw ApiException.bad("Choose exactly one replacement file");
    return request(HttpMethod.POST, source(workspace, id) + "/replace", parts(files));
  }

  public JsonNode retry(Long workspace, String id) {
    tenant.manage(workspace);
    return request(HttpMethod.POST, source(workspace, id) + "/retry", null);
  }

  public JsonNode delete(Long workspace, String id) {
    tenant.manage(workspace);
    return request(HttpMethod.DELETE, source(workspace, id), null);
  }

  public JsonNode publish(Long workspace, String id, boolean publish) {
    tenant.manage(workspace);
    return request(HttpMethod.POST, source(workspace, id) + (publish ? "/publish" : "/unpublish"), null);
  }

  private String root(Long workspace) {
    return "/v1/workspaces/" + workspace;
  }

  private String source(Long workspace, String id) {
    try {
      if (!UUID.fromString(id).toString().equalsIgnoreCase(id))
        throw new IllegalArgumentException();
    } catch (IllegalArgumentException exception) {
      throw ApiException.bad("Source ID must be a UUID");
    }
    return root(workspace) + "/sources/" + id;
  }

  private LinkedMultiValueMap<String, Object> parts(List<MultipartFile> files) {
    if (files == null || files.isEmpty() || files.size() > 20)
      throw ApiException.bad("Choose between 1 and 20 files per batch");
    var parts = new LinkedMultiValueMap<String, Object>();
    for (var file : files) parts.add("files", file.getResource());
    return parts;
  }

  private JsonNode request(HttpMethod method, String path, Object body) {
    if (token == null || token.isBlank())
      throw new ApiException(503, "INGESTION_NOT_CONFIGURED",
          "Knowledge ingestion is not configured. Set RAG_SERVICE_URL and RAG_SERVICE_TOKEN on the CRM and the same RAG_SERVICE_TOKEN on the knowledge service.");
    try {
      // URI builder input is already encoded; expand through a URI to avoid double encoding.
      var request = client.method(method).uri(builder -> builder.build().resolve(path)).headers(headers -> {
        headers.setBearerAuth(token);
        headers.set("X-Actor-Id", tenant.user().toString());
      }).accept(MediaType.APPLICATION_JSON);
      if (body != null) request.contentType(MediaType.MULTIPART_FORM_DATA).body(body);
      var response = request.retrieve().body(JsonNode.class);
      if (response == null)
        throw new ApiException(502, "INGESTION_INVALID_RESPONSE", "Knowledge ingestion returned an empty response.");
      return response;
    } catch (RestClientResponseException exception) {
      int status = exception.getStatusCode().value();
      if (status == 401 || status == 403)
        throw new ApiException(503, "INGESTION_CONFIGURATION_ERROR",
            "Knowledge ingestion authentication failed. Check the service token configuration.");
      if (status == 404)
        throw new ApiException(404, "INGESTION_NOT_FOUND", "Source or knowledge workspace was not found.");
      if (status == 409)
        throw new ApiException(409, "INGESTION_CONFLICT", "This source has an active job or cannot perform that action in its current state. Refresh its status.");
      if (status == 413)
        throw new ApiException(413, "INGESTION_UPLOAD_TOO_LARGE", "Upload exceeds the allowed file or batch size.");
      if (status == 400 || status == 422)
        throw ApiException.bad("Knowledge ingestion rejected this request. Check the file type, size, and source status.");
      throw new ApiException(503, "INGESTION_UNAVAILABLE", "Knowledge ingestion is temporarily unavailable. Try again later.");
    } catch (RestClientException exception) {
      throw new ApiException(503, "INGESTION_UNAVAILABLE", "Unable to reach knowledge ingestion. Check that the ingestion service is running.");
    }
  }
}
