package com.estraos.service;

import static org.junit.jupiter.api.Assertions.*;

import com.estraos.integration.RagServiceClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.*;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;

/** File management files become Projects & inventory; swaps update them and deletes withdraw them. */
@SpringBootTest
@ActiveProfiles({"demo", "test"})
class KnowledgeInventoryImportTest {
  static PostgreSQLContainer<?> postgres;

  @DynamicPropertySource
  static void config(DynamicPropertyRegistry r) {
    String external = System.getenv("TEST_DATABASE_URL");
    if (external == null || external.isBlank()) {
      postgres = new PostgreSQLContainer<>("postgres:17-alpine");
      postgres.start();
      r.add("spring.datasource.url", postgres::getJdbcUrl);
      r.add("spring.datasource.username", postgres::getUsername);
      r.add("spring.datasource.password", postgres::getPassword);
    } else {
      r.add("spring.datasource.url", () -> external);
      r.add("spring.datasource.username", () -> System.getenv("TEST_DATABASE_USERNAME"));
      r.add("spring.datasource.password", () -> System.getenv("TEST_DATABASE_PASSWORD"));
    }
    r.add("app.jwt-secret", () -> UUID.randomUUID().toString() + UUID.randomUUID());
    r.add("app.demo-password", () -> UUID.randomUUID() + "A!");
    r.add("spring.flyway.enabled", () -> true);
    r.add("app.integrations.mode", () -> "mock");
    r.add("app.integrations.rag.url", () -> "");
    r.add("app.integrations.voice.url", () -> "");
    r.add("app.integrations.notification.url", () -> "");
    r.add("app.notifications.reminders-enabled", () -> false);
    r.add("app.knowledge.sync-enabled", () -> false);
    r.add("app.knowledge.import-enabled", () -> false);
    r.add("app.calls.scheduler-enabled", () -> false);
  }

  @AfterAll
  static void stop() {
    if (postgres != null) postgres.stop();
  }

  @Autowired NamedParameterJdbcTemplate db;
  @Autowired TransactionTemplate tx;
  @Autowired ObjectMapper json;
  FakeRag rag;
  KnowledgeInventoryImport importer;
  Long ws;
  final String fileA = UUID.randomUUID().toString();
  final String fileB = UUID.randomUUID().toString();

  @BeforeEach
  void setUp() {
    rag = new FakeRag();
    importer = new KnowledgeInventoryImport(db, rag, tx, json);
    // A fresh workspace per test, so imports never meet another test's data.
    Long owner = db.queryForObject("SELECT id FROM users ORDER BY id LIMIT 1", Map.of(), Long.class);
    ws = db.queryForObject("INSERT INTO workspaces(name) VALUES (:name) RETURNING id",
        Map.of("name", "Import " + UUID.randomUUID()), Long.class);
    assertNotNull(owner);
  }

  static Map<String, Object> listing(String ref, String transaction, String locality, int bhk, double area, long price) {
    Map<String, Object> l = new LinkedHashMap<>();
    l.put("ref", ref); l.put("transaction", transaction); l.put("locality", locality); l.put("city", "Pune");
    l.put("propertyType", bhk + " BHK Apartment"); l.put("configuration", bhk + " BHK"); l.put("bhk", bhk);
    l.put("areaSqft", area); l.put("priceInr", price); l.put("priceText", "as printed");
    l.put("amenities", List.of("Lift", "CCTV"));
    return l;
  }

  static Map<String, Object> extraction(List<Map<String, Object>> projects, List<Map<String, Object>> listings) {
    return Map.of("city", "Pune", "projects", projects, "listings", listings, "warnings", List.of());
  }

  List<Map<String, Object>> units() {
    return db.queryForList("SELECT u.unit_number, u.status, u.price, u.area, u.bhk, u.transaction_type,"
        + " p.name AS project, p.status AS project_status FROM units u JOIN projects p ON p.id=u.project_id"
        + " WHERE u.workspace_id=:ws ORDER BY u.unit_number", Map.of("ws", ws));
  }

  Map<String, Object> unit(String number) {
    return units().stream().filter(u -> number.equals(u.get("unit_number"))).findFirst().orElseThrow();
  }

  @Test
  void listingsBecomeOneProjectPerLocalityAndNamedProjectsKeepTheirName() {
    var shivalik = new LinkedHashMap<String, Object>(Map.of("name", "Shivalik Sky", "developer", "Shivalik Developers",
        "location", "South Bopal, Ahmedabad", "possession", "December 2027", "reraId", "PR/GJ/123",
        "amenities", List.of("Swimming pool", "Gym")));
    var config = new LinkedHashMap<String, Object>(Map.of("projectName", "Shivalik Sky", "configuration", "2 BHK Type A",
        "bhk", 2, "areaSqft", 1250, "priceInr", 7_200_000, "transaction", "SALE"));
    rag.publish(fileA, 1, "pune.csv", extraction(List.of(shivalik), List.of(
        listing("PUN-0001", "RENT", "Aundh", 1, 465, 21_526),
        listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_920_000),
        listing("PUN-0004", "SALE", "Baner", 3, 1194, 10_500_000),
        config)));
    importer.syncWorkspace(ws, false);

    assertEquals("RENT", unit("PUN-0001").get("transaction_type"));
    assertEquals(0, new BigDecimal("21526").compareTo((BigDecimal) unit("PUN-0001").get("price")));
    assertEquals("Aundh listings", unit("PUN-0003").get("project"));
    assertEquals("Baner listings", unit("PUN-0004").get("project"));
    assertEquals("Shivalik Sky", unit("2 BHK Type A").get("project"));
    var project = db.queryForMap("SELECT data->>'location' AS location, data->>'possessionDate' AS possession,"
        + " data->>'developer' AS developer FROM projects WHERE workspace_id=:ws AND name='Shivalik Sky'", Map.of("ws", ws));
    assertEquals("South Bopal, Ahmedabad", project.get("location"));
    assertEquals("2027-12-01", project.get("possession"));
    assertEquals("Shivalik Developers", project.get("developer"));
    assertEquals("Aundh, Pune", db.queryForObject("SELECT data->>'location' FROM projects WHERE workspace_id=:ws"
        + " AND name='Aundh listings'", Map.of("ws", ws), String.class));
    var row = importer.imports(ws).getFirst();
    assertEquals("IMPORTED", row.get("status"));
    assertEquals(4, row.get("units"));
  }

  @Test
  void theSameListingInTwoFilesIsOneUnitAndStaysWhileEitherFileHasIt() {
    rag.publish(fileA, 1, "pune.csv", extraction(List.of(), List.of(
        listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_920_000), listing("PUN-0009", "SALE", "Aundh", 2, 900, 8_000_000))));
    rag.publish(fileB, 1, "pack_01.pdf", extraction(List.of(), List.of(listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_920_000))));
    importer.syncWorkspace(ws, false);
    assertEquals(2, units().size());

    rag.delete(fileA);
    importer.syncWorkspace(ws, false);
    assertEquals("AVAILABLE", unit("PUN-0003").get("status"), "still in pack_01.pdf");
    assertEquals("UNAVAILABLE", unit("PUN-0009").get("status"), "only the deleted file had it");
    assertEquals("ACTIVE", unit("PUN-0003").get("project_status"));

    rag.delete(fileB);
    importer.syncWorkspace(ws, false);
    assertEquals("UNAVAILABLE", unit("PUN-0003").get("status"));
    assertEquals("INACTIVE", unit("PUN-0003").get("project_status"), "an emptied imported project leaves the list");
    assertTrue(importer.imports(ws).stream().allMatch(r -> "REMOVED".equals(r.get("status"))));
  }

  @Test
  void aSwappedFileUpdatesPricesAndWithdrawsWhatItNoLongerHas() {
    rag.publish(fileA, 1, "pune.csv", extraction(List.of(), List.of(
        listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_920_000), listing("PUN-0009", "SALE", "Aundh", 2, 900, 8_000_000))));
    importer.syncWorkspace(ws, false);
    rag.publish(fileA, 2, "pune_v2.csv", extraction(List.of(), List.of(listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_500_000))));
    importer.syncWorkspace(ws, false);
    assertEquals(0, new BigDecimal("7500000").compareTo((BigDecimal) unit("PUN-0003").get("price")));
    assertEquals("UNAVAILABLE", unit("PUN-0009").get("status"));

    rag.publish(fileA, 3, "pune_v3.csv", extraction(List.of(), List.of(
        listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_500_000), listing("PUN-0009", "SALE", "Aundh", 2, 900, 8_000_000))));
    importer.syncWorkspace(ws, false);
    assertEquals("AVAILABLE", unit("PUN-0009").get("status"), "back on the market when the file has it again");
  }

  @Test
  void aUnitMarkedSoldInTheCrmStaysSold() {
    rag.publish(fileA, 1, "pune.csv", extraction(List.of(), List.of(listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_920_000))));
    importer.syncWorkspace(ws, false);
    db.update("UPDATE units SET status='SOLD' WHERE workspace_id=:ws", Map.of("ws", ws));
    rag.publish(fileA, 2, "pune.csv", extraction(List.of(), List.of(listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_900_000))));
    importer.syncWorkspace(ws, false);
    assertEquals("SOLD", unit("PUN-0003").get("status"));
    rag.delete(fileA);
    importer.syncWorkspace(ws, false);
    assertEquals("SOLD", unit("PUN-0003").get("status"));
  }

  @Test
  void aProjectCreatedInTheCrmGetsTheFilesUnitsAndIsNeverRetired() {
    db.update("INSERT INTO projects(workspace_id,name,status,data) VALUES (:ws,'Skyline Crest','ACTIVE',"
        + "'{\"location\":\"Hinjewadi Phase 2, Pune\",\"description\":\"Typed in the CRM\"}')", Map.of("ws", ws));
    var config = new LinkedHashMap<String, Object>(Map.of("projectName", "Skyline Crest", "configuration", "2 BHK",
        "bhk", 2, "areaSqft", 780, "priceInr", 7_650_000, "transaction", "SALE"));
    rag.publish(fileA, 1, "skyline.pdf", extraction(List.of(Map.of("name", "Skyline Crest", "description", "From the file")),
        List.of(config)));
    importer.syncWorkspace(ws, false);
    assertEquals(1, db.queryForObject("SELECT count(*) FROM projects WHERE workspace_id=:ws", Map.of("ws", ws), Integer.class));
    assertEquals("Typed in the CRM", db.queryForObject("SELECT data->>'description' FROM projects WHERE workspace_id=:ws",
        Map.of("ws", ws), String.class), "what someone typed is never overwritten");
    rag.delete(fileA);
    importer.syncWorkspace(ws, false);
    assertEquals("ACTIVE", db.queryForObject("SELECT status FROM projects WHERE workspace_id=:ws", Map.of("ws", ws), String.class));
  }

  @Test
  void aFileStillBeingReadIsPendingAndASettledFileIsNotReadAgain() {
    rag.queued.add(fileA);
    rag.publish(fileA, 1, "pune.csv", extraction(List.of(), List.of(listing("PUN-0003", "SALE", "Aundh", 2, 829, 7_920_000))));
    importer.syncWorkspace(ws, false);
    assertEquals("PENDING", importer.imports(ws).getFirst().get("status"));
    rag.queued.clear();
    importer.syncWorkspace(ws, false);
    int reads = rag.reads;
    importer.syncWorkspace(ws, false);
    assertEquals(reads, rag.reads, "an imported file at the same version is not fetched again");
  }

  @Test
  void possessionTextBecomesADate() {
    assertEquals("2027-12-01", KnowledgeInventoryImport.possessionDate("December 2027").toString());
    assertEquals("2026-04-01", KnowledgeInventoryImport.possessionDate("Q2 2026").toString());
    assertNull(KnowledgeInventoryImport.possessionDate("Ready to move"));
  }

  /** Stands in for the knowledge service: published sources and what was read from them. */
  static final class FakeRag implements RagServiceClient {
    final Map<String, Map<String, Object>> sources = new LinkedHashMap<>();
    final Set<String> queued = new HashSet<>();
    int reads;

    void publish(String id, int version, String file, Map<String, Object> extraction) {
      sources.put(id, Map.of("id", id, "version", version, "status", "PUBLISHED", "fileName", file, "extraction", extraction));
    }

    void delete(String id) { sources.remove(id); }

    public Map<String, Object> listSources(Long workspaceId, int page, int size) {
      List<Map<String, Object>> items = new ArrayList<>();
      for (var s : sources.values()) {
        Map<String, Object> item = new HashMap<>(s);
        item.remove("extraction");
        item.put("crmDocumentId", null);
        items.add(item);
      }
      return Map.of("items", page == 0 ? items : List.of());
    }

    public Map<String, Object> getExtraction(Long workspaceId, String sourceId, boolean retry) {
      reads++;
      var s = sources.get(sourceId);
      if (s == null) return Map.of("sourceId", sourceId, "status", "NOT_PUBLISHED");
      if (queued.contains(sourceId))
        return Map.of("sourceId", sourceId, "status", "QUEUED", "version", s.get("version"), "fileName", s.get("fileName"));
      return Map.of("sourceId", sourceId, "status", "DONE", "version", s.get("version"), "fileName", s.get("fileName"),
          "extraction", s.get("extraction"));
    }

    public Map<String, Object> searchKnowledgeBase(Map<String, Object> r) { throw new UnsupportedOperationException(); }
    public Map<String, Object> indexPublishedContent(Map<String, Object> r) { throw new UnsupportedOperationException(); }
    public Map<String, Object> reindexDocument(Map<String, Object> r) { throw new UnsupportedOperationException(); }
    public Map<String, Object> getProcessingStatus(Map<String, Object> r) { throw new UnsupportedOperationException(); }
    public Map<String, Object> unpublishContent(Map<String, Object> r) { throw new UnsupportedOperationException(); }
    public Map<String, Object> uploadSource(Map<String, Object> r, String f, String c, byte[] b) { throw new UnsupportedOperationException(); }
    public Map<String, Object> getSource(Map<String, Object> r) { throw new UnsupportedOperationException(); }
    public Map<String, Object> deleteSource(Map<String, Object> r) { throw new UnsupportedOperationException(); }
  }
}
