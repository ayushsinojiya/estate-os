package com.estraos;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;

import com.estraos.calls.CallingHours;
import com.estraos.calls.OutboundCallScheduler;
import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.*;
import org.springframework.test.web.servlet.*;
import org.testcontainers.containers.PostgreSQLContainer;

/**
 * The CRM additions the voice agent depends on: bookable slots and automatic agent assignment,
 * callbacks, do-not-call, scheduled outbound calls, the extended call record and WhatsApp.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles({"demo", "test"})
class VoiceCrmIntegrationTest {
  static PostgreSQLContainer<?> postgres;
  static final String PASSWORD = UUID.randomUUID() + "A!";
  static final String APP_SECRET = "whatsapp-app-secret-for-tests";
  static final String JWT_SECRET = UUID.randomUUID().toString() + UUID.randomUUID();

  @DynamicPropertySource
  static void config(DynamicPropertyRegistry r) {
    postgres = new PostgreSQLContainer<>("postgres:17-alpine");
    postgres.start();
    r.add("spring.datasource.url", postgres::getJdbcUrl);
    r.add("spring.datasource.username", postgres::getUsername);
    r.add("spring.datasource.password", postgres::getPassword);
    r.add("app.jwt-secret", () -> JWT_SECRET);
    r.add("app.demo-password", () -> PASSWORD);
    r.add("spring.flyway.enabled", () -> true);
    r.add("app.integrations.mode", () -> "mock");
    r.add("app.notifications.reminders-enabled", () -> false);
    r.add("app.knowledge.sync-enabled", () -> false);
    r.add("app.calls.scheduler-enabled", () -> false);
    r.add("app.whatsapp.app-secret", () -> APP_SECRET);
  }

  @AfterAll
  static void stop() {
    if (postgres != null) postgres.stop();
  }

  @Autowired MockMvc mvc;
  @Autowired ObjectMapper json;
  @Autowired JdbcTemplate db;
  @Autowired PasswordEncoder passwords;
  @Autowired OutboundCallScheduler scheduler;
  String token, ws, projectId;
  static final ZoneId IST = CallingHours.IST;

  @BeforeEach
  void login() throws Exception {
    JsonNode auth = send("POST", "/auth/login", Map.of("email", "admin@estraos.demo", "password", PASSWORD), null, 200);
    token = auth.get("token").asText();
    ws = auth.get("workspaces").get(0).get("id").asText();
    projectId = send("GET", "/projects?size=100", null, ws, 200).get("items").get(0).get("id").asText();
  }

  JsonNode send(String method, String path, Object body, String workspace, int expected) throws Exception {
    var request = switch (method) {
      case "POST" -> post("/api/v1" + path);
      case "PUT" -> put("/api/v1" + path);
      case "PATCH" -> patch("/api/v1" + path);
      case "DELETE" -> delete("/api/v1" + path);
      default -> get("/api/v1" + path);
    };
    request.contentType(MediaType.APPLICATION_JSON);
    if (body != null) request.content(json.writeValueAsBytes(body));
    if (token != null) request.header("Authorization", "Bearer " + token);
    if (workspace != null) request.header("X-Workspace-Id", workspace);
    var result = mvc.perform(request).andReturn();
    assertEquals(expected, result.getResponse().getStatus(), method + " " + path + " " + result.getResponse().getContentAsString());
    String content = result.getResponse().getContentAsString();
    return content.isBlank() ? json.nullNode() : json.readTree(content);
  }

  /** A fresh project with its own agents and visiting hours, so tests do not share capacity. */
  String project(int capacity, String... agentIds) throws Exception {
    String id = send("POST", "/projects", Map.of("name", "Slot test " + UUID.randomUUID(), "location", "Baner, Pune"),
        ws, 201).get("id").asText();
    send("PUT", "/projects/" + id + "/visit-slots", Map.of("windows", List.of(Map.of(
        "days", List.of(1, 2, 3, 4, 5, 6, 7), "start", "10:00", "end", "12:00", "slotMinutes", 60, "capacity", capacity))),
        ws, 200);
    if (agentIds.length > 0)
      send("PUT", "/projects/" + id + "/agents", Map.of("agents",
          Arrays.stream(agentIds).map(a -> Map.of("userId", a, "available", true)).toList()), ws, 200);
    return id;
  }

  String agent(String name) {
    Long role = db.queryForObject("SELECT id FROM roles WHERE name='REAL_ESTATE_AGENT'", Long.class);
    Long user = db.queryForObject("INSERT INTO users(name,email,password_hash,phone) VALUES (?,?,?,?) RETURNING id",
        Long.class, name, UUID.randomUUID() + "@agents.example.invalid", passwords.encode(PASSWORD), "+919800000000");
    db.update("INSERT INTO workspace_members(workspace_id,user_id,role_id) VALUES (?,?,?)", Long.valueOf(ws), user, role);
    return user.toString();
  }

  String lead() throws Exception {
    String digits = Long.toString(System.nanoTime());
    return send("POST", "/leads/find-or-create", Map.of("phone", "98" + digits.substring(digits.length() - 8)), ws, 200)
        .get("id").asText();
  }

  static LocalDate inDays(int days) {
    return LocalDate.now(IST).plusDays(days);
  }

  static String at(LocalDate date, int hour) {
    return date.atTime(hour, 0).atZone(IST).toInstant().toString();
  }

  JsonNode book(String lead, String project, String slot, int expected) throws Exception {
    return send("POST", "/voice/visits", Map.of("leadId", lead, "projectId", project, "slotStart", slot,
        "language", "hi", "callId", "call-" + UUID.randomUUID()), ws, expected);
  }

  // ---------------------------------------------------------------- slots and assignment

  @Test
  void slotsAreComputedInIstAndCapacityIsEnforced() throws Exception {
    String a = agent("Asha Agent"), b = agent("Bina Agent");
    String project = project(2, a, b);
    LocalDate day = inDays(3);
    JsonNode slots = send("GET", "/voice/projects/" + project + "/slots?from=" + day + "&days=1", null, ws, 200);
    assertEquals(2, slots.get("slots").size());
    JsonNode first = slots.get("slots").get(0);
    assertEquals(at(day, 10), first.get("start").asText());
    assertTrue(first.get("label").asText().endsWith(" 10 AM"));
    assertTrue(first.get("startLocal").asText().endsWith("+05:30"));
    assertEquals(2, first.get("remaining").asInt());

    book(lead(), project, at(day, 10), 201);
    book(lead(), project, at(day, 10), 201);
    JsonNode full = book(lead(), project, at(day, 10), 409);
    assertEquals("SLOT_UNAVAILABLE", full.get("code").asText());
    JsonNode after = send("GET", "/voice/projects/" + project + "/slots?from=" + day + "&days=1", null, ws, 200);
    assertEquals(1, after.get("slots").size(), "the full 10 AM slot is no longer offered");
    // A slot that is not on the template is refused too.
    book(lead(), project, day.atTime(10, 30).atZone(IST).toInstant().toString(), 409);
  }

  @Test
  void blackoutsRemoveSlots() throws Exception {
    String project = project(3, agent("Chetan Agent"));
    LocalDate day = inDays(4);
    send("POST", "/projects/" + project + "/blackouts", Map.of("startsAt", at(day, 0), "endsAt", at(day.plusDays(1), 0),
        "reason", "Diwali"), ws, 201);
    assertEquals(0, send("GET", "/voice/projects/" + project + "/slots?from=" + day + "&days=1", null, ws, 200)
        .get("slots").size());
  }

  @Test
  void twoCallersCannotBothTakeTheLastSeat() throws Exception {
    String project = project(1, agent("Deepa Agent"), agent("Esha Agent"));
    String slot = at(inDays(5), 11);
    List<String> leads = List.of(lead(), lead());
    Callable<Integer> first = () -> status(leads.get(0), project, slot);
    Callable<Integer> second = () -> status(leads.get(1), project, slot);
    try (var pool = Executors.newFixedThreadPool(2)) {
      List<Integer> statuses = new ArrayList<>();
      for (var future : pool.invokeAll(List.of(first, second))) statuses.add(future.get());
      Collections.sort(statuses);
      assertEquals(List.of(201, 409), statuses);
    }
  }

  int status(String lead, String project, String slot) throws Exception {
    return mvc.perform(post("/api/v1/voice/visits").header("Authorization", "Bearer " + token).header("X-Workspace-Id", ws)
            .contentType(MediaType.APPLICATION_JSON)
            .content(json.writeValueAsBytes(Map.of("leadId", lead, "projectId", project, "slotStart", slot))))
        .andReturn().getResponse().getStatus();
  }

  @Test
  void agentsAreAssignedRoundRobinSkippingBusyOnesAndFlaggedWhenNoneIsFree() throws Exception {
    String a = agent("Farah Agent"), b = agent("Gita Agent");
    String project = project(3, a, b);
    LocalDate day = inDays(6);
    JsonNode one = book(lead(), project, at(day, 10), 201);
    JsonNode two = book(lead(), project, at(day, 10), 201);
    JsonNode three = book(lead(), project, at(day, 11), 201);
    assertEquals(a, one.get("agentId").asText());
    assertEquals(b, two.get("agentId").asText(), "the first agent is busy at 10, so the second takes it");
    assertEquals(a, three.get("agentId").asText(), "round-robin: the agent assigned longest ago goes next");
    assertEquals("CONFIRMED", one.get("status").asText());
    assertEquals("Farah Agent", one.get("agentName").asText());
    assertEquals("VOICE_AGENT", one.get("bookedBy").asText());

    // Both agents are busy at 10 AM: the visit is still booked, provisionally, for review.
    JsonNode flagged = book(lead(), project, at(day, 10), 201);
    assertEquals("REQUESTED", flagged.get("status").asText());
    assertTrue(flagged.get("needsManagerReview").asBoolean());
    assertTrue(db.queryForObject("SELECT count(*) FROM notifications WHERE workspace_id=? AND data->>'type'='VISIT_NEEDS_REVIEW'",
        Long.class, Long.valueOf(ws)) > 0);

    // An agent on leave is skipped.
    send("PUT", "/members/" + a + "/availability", Map.of("available", false), ws, 200);
    assertEquals(b, book(lead(), project, at(day, 11), 201).get("agentId").asText());
  }

  @Test
  void bookingMovesTheLeadForwardAndSchedulesReminders() throws Exception {
    String project = project(3, agent("Hema Agent"));
    String lead = lead();
    JsonNode visit = book(lead, project, at(inDays(3), 11), 201);
    assertEquals("VISIT_PLANNED", send("GET", "/leads/" + lead, null, ws, 200).get("status").asText());
    var reminders = db.queryForList("SELECT data->>'reminder' AS kind, due_at FROM scheduled_calls WHERE workspace_id=? AND"
        + " appointment_id=? AND call_type='VISIT_REMINDER' AND status='SCHEDULED' ORDER BY due_at",
        Long.valueOf(ws), Long.valueOf(visit.get("id").asText()));
    assertEquals(List.of("DAY_BEFORE", "SAME_DAY"), reminders.stream().map(r -> r.get("kind")).toList());
    Instant dayBefore = ((java.sql.Timestamp) reminders.get(0).get("due_at")).toInstant();
    assertEquals(LocalTime.of(18, 0), dayBefore.atZone(IST).toLocalTime());

    // Rescheduling replaces the reminders; cancelling removes them.
    JsonNode moved = send("POST", "/voice/visits/" + visit.get("id").asText() + "/reschedule",
        Map.of("slotStart", at(inDays(4), 10), "reason", "Customer travelling"), ws, 200);
    assertEquals("RESCHEDULED", moved.get("status").asText());
    send("POST", "/voice/visits/" + visit.get("id").asText() + "/confirm", null, ws, 200);
    send("POST", "/voice/visits/" + visit.get("id").asText() + "/cancel", Map.of("reason", "Bought elsewhere"), ws, 200);
    assertEquals(0, db.queryForObject("SELECT count(*) FROM scheduled_calls WHERE appointment_id=? AND status='SCHEDULED'",
        Long.class, Long.valueOf(visit.get("id").asText())));
    send("POST", "/voice/visits/" + visit.get("id").asText() + "/confirm", null, ws, 409);
  }

  // ---------------------------------------------------------------- DNC, callbacks, lead merge

  @Test
  void doNotCallIsRefusedEverywhere() throws Exception {
    String lead = lead();
    String phone = send("GET", "/leads/" + lead, null, ws, 200).get("phone").asText();
    send("POST", "/voice/dnc", Map.of("phone", phone.substring(3), "reason", "Customer asked", "leadId", lead), ws, 200);
    assertTrue(send("GET", "/voice/dnc/check?phone=" + phone, null, ws, 200).get("dnc").asBoolean());
    JsonNode detail = send("GET", "/leads/" + lead, null, ws, 200);
    assertTrue(detail.get("dnc").asBoolean());
    assertEquals("NOT_INTERESTED", detail.get("status").asText());
    JsonNode refused = send("POST", "/calls", Map.of("leadId", lead), ws, 409);
    assertEquals("DO_NOT_CALL", refused.get("code").asText());
  }

  @Test
  void leadMergeAppliesOnlyGivenFieldsAndNeverMovesStatusBack() throws Exception {
    String lead = lead();
    send("PATCH", "/voice/leads/" + lead, Map.of("budgetMax", 12000000, "bhk", List.of(2, 3), "status", "QUALIFIED",
        "purpose", "SELF_USE"), ws, 200);
    JsonNode patched = send("PATCH", "/voice/leads/" + lead, Map.of("location", "Baner", "status", "CONTACTED"), ws, 200);
    assertEquals("QUALIFIED", patched.get("status").asText());
    assertEquals(12000000, patched.get("budgetMax").asInt());
    assertEquals("Baner", patched.get("location").asText());
    assertEquals("SELF_USE", patched.get("purpose").asText());
    send("PATCH", "/voice/leads/" + lead, Map.of("unknownField", 1), ws, 400);
  }

  // ---------------------------------------------------------------- scheduled calls

  String callback(String lead, Instant due) throws Exception {
    return send("POST", "/leads/" + lead + "/callbacks", Map.of("dueAt", due.toString(), "reason", "Call after work"),
        ws, 201).get("id").asText();
  }

  long outboundCalls(String lead) {
    return db.queryForObject("SELECT count(*) FROM voice_sessions WHERE workspace_id=? AND lead_id=? AND data->>'outbound'='true'",
        Long.class, Long.valueOf(ws), Long.valueOf(lead));
  }

  @Test
  void callsDueOutsideCallingHoursAreDeferredTo930() throws Exception {
    String lead = lead();
    String callback = callback(lead, Instant.now().plusSeconds(3600));
    Instant lateNight = inDays(2).atTime(22, 15).atZone(IST).toInstant();
    scheduler.dispatchDue(lateNight); // other tests' rows may be due too; assertions are per lead
    var due = db.queryForObject("SELECT due_at FROM scheduled_calls WHERE callback_id=? AND status='SCHEDULED'",
        java.sql.Timestamp.class, Long.valueOf(callback)).toInstant();
    assertEquals(inDays(3).atTime(9, 30).atZone(IST).toInstant(), due);
    assertEquals(0, outboundCalls(lead));
    scheduler.dispatchDue(inDays(3).atTime(9, 45).atZone(IST).toInstant());
    assertEquals(1, outboundCalls(lead));
    var call = db.queryForMap("SELECT data FROM voice_sessions WHERE lead_id=? AND data->>'outbound'='true'", Long.valueOf(lead));
    JsonNode data = json.readTree(call.get("data").toString());
    assertEquals("CALLBACK", data.get("callType").asText());
  }

  @Test
  void theSchedulerNeverDialsTheSameCallTwice() throws Exception {
    String lead = lead();
    callback(lead, Instant.now().plusSeconds(600));
    Instant now = inDays(2).atTime(11, 0).atZone(IST).toInstant();
    try (var pool = Executors.newFixedThreadPool(3)) {
      for (var f : pool.invokeAll(List.<Callable<Integer>>of(() -> scheduler.dispatchDue(now),
          () -> scheduler.dispatchDue(now), () -> scheduler.dispatchDue(now)))) f.get();
    }
    scheduler.dispatchDue(now.plusSeconds(60));
    assertEquals(1, outboundCalls(lead), "three concurrent dispatchers and a later pass placed one call");
    assertEquals("DIALING", db.queryForObject("SELECT status FROM scheduled_calls WHERE lead_id=?", String.class,
        Long.valueOf(lead)));
  }

  @Test
  void theDailyAttemptCapDefersFurtherCalls() throws Exception {
    String lead = lead();
    Instant now = inDays(2).atTime(12, 0).atZone(IST).toInstant();
    for (int i = 0; i < 3; i++) callback(lead, Instant.now().plusSeconds(600 + i));
    scheduler.dispatchDue(now);
    assertEquals(2, outboundCalls(lead));
    assertEquals(1, db.queryForObject("SELECT count(*) FROM scheduled_calls WHERE lead_id=? AND status='SCHEDULED'"
        + " AND data->>'deferredReason'='DAILY_CAP'", Long.class, Long.valueOf(lead)));
  }

  @Test
  void newWebLeadsGetAFirstCall() throws Exception {
    String suffix = Long.toString(System.nanoTime());
    String lead = send("POST", "/leads", Map.of("name", "Web enquiry", "phone", "+9197" + suffix.substring(suffix.length() - 8),
        "source", "WEBSITE", "language", "mr"), ws, 201).get("id").asText();
    assertEquals(1, db.queryForObject("SELECT count(*) FROM scheduled_calls WHERE lead_id=? AND call_type='OUTBOUND_NEW_LEAD'",
        Long.class, Long.valueOf(lead)));
  }

  // ---------------------------------------------------------------- the extended call record

  Map<String, Object> record(String lead, String callId) {
    Map<String, Object> record = new LinkedHashMap<>();
    record.put("callId", callId);
    record.put("voiceSessionId", callId);
    record.put("leadId", lead);
    record.put("direction", "inbound");
    record.put("durationSeconds", 180);
    record.put("language", "hi");
    record.put("summary", "Wants a 2 BHK, booked a visit.");
    return record;
  }

  @Test
  void aHotCallCreatesAHandoverACallbackAndRecordsConsent() throws Exception {
    String project = project(3, agent("Indu Agent"));
    String lead = lead();
    String callId = "call-" + UUID.randomUUID();
    var visit = send("POST", "/voice/visits", Map.of("leadId", lead, "projectId", project, "slotStart", at(inDays(3), 10),
        "callId", callId), ws, 201);
    Map<String, Object> record = record(lead, callId);
    record.put("projectId", project);
    record.put("callType", "INBOUND");
    record.put("leadTemperature", "HOT");
    record.put("leadScore", 85);
    record.put("handoverRequested", true);
    record.put("handoverReason", "NEGOTIATION");
    record.put("unansweredQuestions", List.of("Is there a festive discount?"));
    record.put("callbackAt", Instant.now().plusSeconds(86400).toString());
    record.put("whatsappConsent", true);
    record.put("whatsappRequests", List.of("VISIT_CONFIRMATION"));
    record.put("citations", List.of("301"));
    JsonNode stored = send("POST", "/calls/ingest", record, ws, 200);
    assertTrue(stored.get("outcomes").has("handoverId"));

    JsonNode detail = send("GET", "/leads/" + lead, null, ws, 200);
    assertEquals("VISIT_PLANNED", detail.get("status").asText(), "a later QUALIFIED never moves a lead back");
    assertTrue(detail.get("whatsappConsent").asBoolean());
    assertTrue(detail.hasNonNull("whatsappConsentAt"));
    assertEquals(1, detail.get("callbacks").size());
    JsonNode handover = detail.get("handovers").get(0);
    assertEquals("PENDING", handover.get("status").asText());
    assertEquals("NEGOTIATION", handover.get("reason").asText());
    assertTrue(handover.get("questions").asText().contains("festive discount"));
    var whatsapp = db.queryForMap("SELECT status, data->>'channel' AS channel, data->>'template' AS template FROM notifications"
        + " WHERE workspace_id=? AND data->>'type'='WHATSAPP_VISIT_CONFIRMATION' AND data->>'resourceId'=?",
        Long.valueOf(ws), visit.get("id").asText());
    assertEquals("WHATSAPP", whatsapp.get("channel"));
    assertEquals("visit_confirmation", whatsapp.get("template"));
    assertEquals("MOCK_DELIVERED", whatsapp.get("status"));

    // Resending the same record (the agent's outbox after a timeout) repeats none of it.
    send("POST", "/calls/ingest", record, ws, 200);
    assertEquals(1, send("GET", "/leads/" + lead, null, ws, 200).get("handovers").size());
    assertEquals(1, db.queryForObject("SELECT count(*) FROM callbacks WHERE lead_id=?", Long.class, Long.valueOf(lead)));
  }

  @Test
  void withoutConsentNoWhatsAppIsSent() throws Exception {
    String project = project(3, agent("Jaya Agent"));
    String lead = lead();
    String callId = "call-" + UUID.randomUUID();
    send("POST", "/voice/visits", Map.of("leadId", lead, "projectId", project, "slotStart", at(inDays(3), 11),
        "callId", callId), ws, 201);
    Map<String, Object> record = record(lead, callId);
    record.put("whatsappRequests", List.of("VISIT_CONFIRMATION"));
    send("POST", "/calls/ingest", record, ws, 200);
    assertEquals(0, db.queryForObject("SELECT count(*) FROM notifications WHERE workspace_id=? AND data->>'channel'='WHATSAPP'"
        + " AND data->>'leadId'=?", Long.class, Long.valueOf(ws), lead));
  }

  @Test
  void aReminderCallRecordsTheVisitOutcome() throws Exception {
    String project = project(3, agent("Kiran Agent"));
    String lead = lead();
    String visit = book(lead, project, at(inDays(3), 10), 201).get("id").asText();
    Map<String, Object> confirm = record(lead, "call-" + UUID.randomUUID());
    confirm.put("callType", "VISIT_REMINDER");
    confirm.put("appointmentId", visit);
    confirm.put("visitOutcome", "CONFIRMED");
    send("POST", "/calls/ingest", confirm, ws, 200);
    JsonNode confirmed = send("GET", "/site-visits/" + visit, null, ws, 200);
    assertEquals("CONFIRMED", confirmed.get("confirmationStatus").asText());

    Map<String, Object> cancel = record(lead, "call-" + UUID.randomUUID());
    cancel.put("callType", "VISIT_REMINDER");
    cancel.put("appointmentId", visit);
    cancel.put("visitOutcome", "CANCELLED");
    send("POST", "/calls/ingest", cancel, ws, 200);
    assertEquals("CANCELLED", send("GET", "/site-visits/" + visit, null, ws, 200).get("status").asText());
    assertEquals(0, db.queryForObject("SELECT count(*) FROM scheduled_calls WHERE appointment_id=? AND status='SCHEDULED'",
        Long.class, Long.valueOf(visit)));
  }

  @Test
  void unknownIngestFieldsAreStillRejected() throws Exception {
    Map<String, Object> record = record(lead(), "call-" + UUID.randomUUID());
    record.put("notAField", true);
    send("POST", "/calls/ingest", record, ws, 400);
    Map<String, Object> bad = record(lead(), "call-" + UUID.randomUUID());
    bad.put("leadTemperature", "LUKEWARM");
    send("POST", "/calls/ingest", bad, ws, 400);
  }

  // ---------------------------------------------------------------- WhatsApp webhook

  @Test
  void whatsappStatusWebhookRequiresAValidSignature() throws Exception {
    db.update("INSERT INTO notifications(workspace_id,status,data) VALUES (?, 'SENT', jsonb_build_object('providerMessageId','wamid.TEST1','channel','WHATSAPP','type','WHATSAPP_BROCHURE'))",
        Long.valueOf(ws));
    byte[] body = ("{\"entry\":[{\"changes\":[{\"value\":{\"statuses\":[{\"id\":\"wamid.TEST1\",\"status\":\"delivered\","
        + "\"timestamp\":\"1700000000\"}]}}]}]}").getBytes(StandardCharsets.UTF_8);
    mvc.perform(post("/api/v1/webhooks/whatsapp").contentType(MediaType.APPLICATION_JSON).content(body)
            .header("X-Hub-Signature-256", "sha256=00"))
        .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isUnauthorized());
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(APP_SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
    String signature = "sha256=" + HexFormat.of().formatHex(mac.doFinal(body));
    mvc.perform(post("/api/v1/webhooks/whatsapp").contentType(MediaType.APPLICATION_JSON).content(body)
            .header("X-Hub-Signature-256", signature))
        .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isOk());
    assertEquals("DELIVERED", db.queryForObject("SELECT status FROM notifications WHERE data->>'providerMessageId'='wamid.TEST1'",
        String.class));
  }

  @Test
  void voiceEndpointsAreWorkspaceScoped() throws Exception {
    JsonNode auth = send("POST", "/auth/login", Map.of("email", "admin@estraos.demo", "password", PASSWORD), null, 200);
    String other = auth.get("workspaces").get(1).get("id").asText();
    send("GET", "/voice/projects/" + projectId + "/slots", null, other, 404);
    send("PATCH", "/voice/leads/" + lead(), Map.of("location", "Baner"), other, 404);
  }
}
