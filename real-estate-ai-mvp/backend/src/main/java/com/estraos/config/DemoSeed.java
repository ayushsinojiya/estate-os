package com.estraos.config;

import static com.estraos.service.EstateService.*;

import com.estraos.repository.TenantRepository;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.*;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** Explicit opt-in, idempotent, fictional development data. Never resets existing data. */
@Component
@Profile("demo")
// Before ServiceAccountProvisioner, so on a fresh database the demo workspace is workspace 1 and
// the voice agent's service account joins it rather than an empty workspace of its own.
@org.springframework.core.annotation.Order(1)
public class DemoSeed implements ApplicationRunner {
  private final JdbcTemplate db;
  private final TenantRepository repo;
  private final PasswordEncoder passwords;
  private final String demoPassword;

  public DemoSeed(
      JdbcTemplate db,
      TenantRepository repo,
      PasswordEncoder passwords,
      @Value("${app.demo-password}") String demoPassword) {
    this.db = db;
    this.repo = repo;
    this.passwords = passwords;
    this.demoPassword = demoPassword;
  }

  @Override
  @Transactional
  public void run(ApplicationArguments args) {
    if (demoPassword == null
        || demoPassword.length() < 12
        || demoPassword.toLowerCase(Locale.ROOT).contains("replace"))
      throw new IllegalStateException(
          "Demo profile requires DEMO_PASSWORD with at least 12 characters; no fixed password is"
              + " shipped");
    db.queryForObject("SELECT pg_advisory_xact_lock(7800123)", Object.class);
    if (Boolean.TRUE.equals(
        db.queryForObject(
            "SELECT EXISTS(SELECT 1 FROM workspaces WHERE demo=true)", Boolean.class))) return;
    Map<String, Long> roles = new HashMap<>();
    for (String name : List.of("ADMIN", "MANAGER", "REAL_ESTATE_AGENT")) {
      Long role =
          db.queryForObject(
              "INSERT INTO roles(name) VALUES (?) ON CONFLICT(name) DO UPDATE SET"
                  + " name=excluded.name RETURNING id",
              Long.class,
              name);
      roles.put(name, role);
    }
    for (String name : List.of("MANAGE_PROPERTY", "MANAGE_CUSTOMER", "VIEW_AUDIT")) {
      Long permission =
          db.queryForObject(
              "INSERT INTO permissions(name) VALUES (?) ON CONFLICT(name) DO UPDATE SET"
                  + " name=excluded.name RETURNING id",
              Long.class,
              name);
      for (var role : roles.entrySet())
        if (!role.getKey().equals("REAL_ESTATE_AGENT") || name.equals("MANAGE_CUSTOMER"))
          db.update(
              "INSERT INTO role_permissions(role_id,permission_id) VALUES (?,?) ON CONFLICT DO"
                  + " NOTHING",
              role.getValue(),
              permission);
    }
    Long ws =
        db.queryForObject(
            "INSERT INTO workspaces(name,demo) VALUES ('Westhaven Realty · Demo',true) RETURNING"
                + " id",
            Long.class);
    Long other =
        db.queryForObject(
            "INSERT INTO workspaces(name,demo) VALUES ('Northstar Realty · Demo',true) RETURNING"
                + " id",
            Long.class);
    String hash = passwords.encode(demoPassword);
    Long admin = user("Aarav Shah", "admin@estraos.demo", hash),
        manager = user("Meera Patel", "manager@estraos.demo", hash),
        agent = user("Riya Desai", "agent@estraos.demo", hash),
        otherAgent = user("Dev Mehta", "agent2@estraos.demo", hash);
    member(ws, admin, roles.get("ADMIN"));
    member(other, admin, roles.get("ADMIN"));
    member(ws, manager, roles.get("MANAGER"));
    member(ws, agent, roles.get("REAL_ESTATE_AGENT"));
    member(other, otherAgent, roles.get("REAL_ESTATE_AGENT"));
    Long secondAgent = user("Kabir Joshi", "agent3@estraos.demo", hash);
    member(ws, secondAgent, roles.get("REAL_ESTATE_AGENT"));
    db.update("UPDATE users SET phone='+919800000101' WHERE id=?", agent);
    db.update("UPDATE users SET phone='+919800000102' WHERE id=?", secondAgent);
    String[] names = {"The Palms Residences", "Riverfront Heights", "Oakwood Gardens"};
    String[] locations = {"Satellite, Ahmedabad", "Paldi, Ahmedabad", "Whitefield, Bengaluru"};
    List<Long> projects = new ArrayList<>(), units = new ArrayList<>();
    for (int i = 0; i < 3; i++) {
      var project =
          repo.save(
              "projects",
              ws,
              null,
              fields(
                  "description",
                  "A thoughtfully planned residential community with open spaces and convenient"
                      + " city connections.",
                  "location",
                  locations[i],
                  "developer",
                  "Westhaven Developers",
                  "possessionDate",
                  "2027-06-30",
                  "amenities",
                  "Clubhouse, landscaped gardens, gym, children's play area",
                  "mediaUrl",
                  null),
              fields("name", names[i], "status", "ACTIVE"));
      Long projectId = id(project.get("id"));
      projects.add(projectId);
      repo.event(
          "project_locations", ws, "project_id", projectId, fields("location", locations[i]));
      repo.event(
          "project_amenities",
          ws,
          "project_id",
          projectId,
          fields("amenities", "Clubhouse, gym, gardens"));
      Long building =
          id(
              repo.save(
                      "buildings",
                      ws,
                      null,
                      Map.of(),
                      fields("project_id", projectId, "name", "Tower A"))
                  .get("id"));
      repo.save(
          "floors",
          ws,
          null,
          Map.of(),
          fields("project_id", projectId, "building_id", building, "number", 3));
      repo.save(
          "unit_types", ws, null, Map.of(), fields("project_id", projectId, "name", "Apartment"));
      for (int j = 0; j < 4; j++) {
        String state = j == 3 ? "RESERVED" : "AVAILABLE";
        var unit =
            repo.save(
                "units",
                ws,
                null,
                fields("floor", 3, "facing", j % 2 == 0 ? "EAST" : "WEST"),
                fields(
                    "project_id",
                    projectId,
                    "building_id",
                    building,
                    "unit_number",
                    "A-30" + (j + 1),
                    "status",
                    state,
                    "price",
                    new BigDecimal(6500000 + i * 1500000 + j * 900000),
                    "area",
                    new BigDecimal(1050 + j * 200),
                    "bhk",
                    j < 2 ? 2 : 3,
                    "property_type",
                    "APARTMENT"));
        Long unitId = id(unit.get("id"));
        units.add(unitId);
        repo.event(
            "unit_status_history",
            ws,
            "unit_id",
            unitId,
            fields("status", state, "userId", admin.toString()));
        repo.event(
            "unit_prices",
            ws,
            "unit_id",
            unitId,
            fields("price", unit.get("price"), "currency", "INR"));
      }
    }
    seedVisiting(ws, projects, List.of(agent, secondAgent));
    seedKnowledge(ws, projects.subList(0, 2), names, locations);
    String[] people = {
      "Kavya Joshi",
      "Vikram Rao",
      "Ananya Shah",
      "Nikhil Patel",
      "Priya Mehta",
      "Rahul Desai",
      "Ishita Shah",
      "Amit Kulkarni"
    };
    String[] states = {
      "QUALIFIED",
      "NEW",
      "VISIT_PLANNED",
      "CONTACTED",
      "HANDED_OVER",
      "QUALIFIED",
      "NEW",
      "VISIT_COMPLETED"
    };
    List<Long> leads = new ArrayList<>();
    for (int i = 0; i < people.length; i++) {
      var lead =
          repo.save(
              "leads",
              ws,
              null,
              fields(
                  "language",
                  List.of("en", "hi", "gu", "mr").get(i % 4),
                  "intent",
                  "BUY",
                  "budgetMin",
                  6000000,
                  "budgetMax",
                  12000000,
                  "location",
                  "Ahmedabad",
                  "propertyType",
                  "APARTMENT",
                  "bhk",
                  2,
                  "areaMin",
                  900,
                  "areaMax",
                  1800,
                  "possessionTimeline",
                  "Within 12 months",
                  "purpose",
                  "SELF_USE",
                  "urgency",
                  "MEDIUM",
                  "source",
                  i % 2 == 0 ? "WEBSITE" : "REFERRAL",
                  "tags",
                  i % 2 == 0 ? "First-time buyer" : "Family",
                  "notes",
                  "Fictional demo customer. Prefers a well-connected community.",
                  "followUpAt",
                  Instant.now().plusSeconds((i + 1) * 7200).toString()),
              fields(
                  "name",
                  people[i],
                  "phone",
                  "+9190000010" + String.format("%02d", i),
                  "email",
                  "customer" + i + "@example.invalid",
                  "status",
                  states[i],
                  "assigned_agent_id",
                  agent));
      Long leadId = id(lead.get("id"));
      leads.add(leadId);
      repo.event(
          "lead_activities",
          ws,
          "lead_id",
          leadId,
          fields(
              "action",
              "LEAD_CREATED",
              "description",
              "Fictional demo inquiry captured",
              "userId",
              admin.toString()));
      repo.event(
          "lead_notes",
          ws,
          "lead_id",
          leadId,
          fields(
              "text",
              "Customer is interested in a weekend site visit.",
              "userId",
              agent.toString()));
      repo.event(
          "lead_preferences", ws, "lead_id", leadId, fields("budgetMax", 12000000, "bhk", 2));
      repo.event("lead_status_history", ws, "lead_id", leadId, fields("status", states[i]));
    }
    for (int i = 0; i < 4; i++) {
      String language = List.of("en", "hi", "gu", "mr").get(i);
      String text =
          List.of(
                  "The Palms offers two and three bedroom apartments, landscaped gardens and a"
                      + " clubhouse. Contact your agent for confirmed pricing.",
                  "द पाल्म्स में दो और तीन बेडरूम अपार्टमेंट, बगीचे और क्लब हाउस उपलब्ध हैं।",
                  "ધ પાલ્મ્સમાં બે અને ત્રણ બેડરૂમ એપાર્ટમેન્ટ, બગીચા અને ક્લબહાઉસ છે.",
                  "द पाल्म्समध्ये दोन आणि तीन बेडरूम अपार्टमेंट, बागा आणि क्लब हाऊस आहेत.")
              .get(i);
      var doc =
          repo.save(
              "property_documents",
              ws,
              null,
              fields(
                  "fileName",
                  "palms-brochure-" + language + ".pdf",
                  "storageReference",
                  "demo://brochures/palms-" + language + ".pdf",
                  "storageMode",
                  "DEMO_METADATA_ONLY",
                  "language",
                  language,
                  "pageReference",
                  "Page 1",
                  "content",
                  text,
                  "version",
                  1,
                  "processingStatus",
                  "NOT_INDEXED",
                  "mock",
                  true),
              fields(
                  "project_id",
                  projects.getFirst(),
                  "title",
                  "The Palms brochure · " + language,
                  "status",
                  i == 0 ? "PUBLISHED" : "DRAFT"));
      Long docId = id(doc.get("id"));
      repo.event(
          "property_content_versions",
          ws,
          "document_id",
          docId,
          fields("version", 1, "content", text, "language", language, "status", doc.get("status")));
      repo.event(
          "property_content",
          ws,
          "document_id",
          docId,
          fields("version", 1, "content", text, "status", doc.get("status")));
    }
    for (int i = 0; i < 3; i++) {
      var call =
          repo.save(
              "voice_sessions",
              ws,
              null,
              fields(
                  "externalId",
                  "demo-seeded-call-" + i,
                  "leadName",
                  people[i],
                  "transcript",
                  "Customer: I am looking for a two bedroom home in Ahmedabad.\n"
                      + "Assistant: I have recorded your preferences for the real-estate agent.",
                  "summary",
                  "Customer prefers a 2 BHK apartment with a budget up to ₹1.2 crore. Available for"
                      + " a weekend visit.",
                  "requirements",
                  fields("bhk", 2, "budgetMax", 12000000, "location", "Ahmedabad"),
                  "outcome",
                  "QUALIFIED",
                  "mock",
                  true),
              fields("lead_id", leads.get(i), "status", "COMPLETED"));
      Long callId = id(call.get("id"));
      repo.event(
          "voice_transcripts",
          ws,
          "voice_session_id",
          callId,
          fields("transcript", call.get("transcript")));
      repo.event(
          "voice_summaries",
          ws,
          "voice_session_id",
          callId,
          fields("summary", call.get("summary")));
    }
    Long appointment = null;
    for (int i = 0; i < 3; i++) {
      Instant at = Instant.now().plusSeconds((i + 1) * 86400);
      var visit =
          repo.save(
              "appointments",
              ws,
              null,
              fields(
                  "notes",
                  "Demo site visit",
                  "leadName",
                  people[i],
                  "projectName",
                  names[i],
                  "confirmationStatus",
                  "PENDING",
                  "notificationStatus",
                  "MOCK_DELIVERED"),
              fields(
                  "project_id",
                  projects.get(i),
                  "lead_id",
                  leads.get(i),
                  "unit_id",
                  units.get(i * 4),
                  "agent_id",
                  agent,
                  "scheduled_at",
                  Timestamp.from(at),
                  "duration_minutes",
                  60,
                  "status",
                  "CONFIRMED"));
      if (i == 0) appointment = id(visit.get("id"));
      repo.event(
          "appointment_status_history",
          ws,
          "appointment_id",
          id(visit.get("id")),
          fields("status", "CONFIRMED", "scheduledAt", at.toString()));
    }
    repo.save(
        "lead_recommendations",
        ws,
        null,
        fields("reason", "Available 2 BHK within the demo customer's budget"),
        fields("lead_id", leads.getFirst(), "unit_id", units.getFirst()));
    repo.save(
        "handover_records",
        ws,
        null,
        fields(
            "notes",
            "Review customer preferences and confirm site visit.",
            "questions",
            "What is the expected maintenance charge?",
            "handoverAt",
            Instant.now().toString(),
            "leadName",
            people[0],
            "scopeNotice",
            "The human real-estate agent handles all later buying and legal activities."),
        fields(
            "lead_id",
            leads.getFirst(),
            "agent_id",
            agent,
            "project_id",
            projects.getFirst(),
            "unit_id",
            units.getFirst(),
            "appointment_id",
            appointment,
            "status",
            "ASSIGNED"));
    repo.save(
        "notifications",
        ws,
        null,
        fields(
            "type",
            "HANDOVER",
            "title",
            "New customer handover",
            "message",
            "Kavya Joshi's preferences are ready for review.",
            "read",
            false,
            "mock",
            true),
        fields("user_id", agent, "status", "MOCK_DELIVERED"));
    repo.save(
        "audit_logs",
        ws,
        null,
        fields("description", "Fictional demo data initialized"),
        fields(
            "user_id",
            admin,
            "action",
            "DEMO_INITIALIZED",
            "entity_type",
            "WORKSPACE",
            "entity_id",
            ws));
    repo.save(
        "projects",
        other,
        null,
        fields(
            "location",
            "Pune",
            "description",
            "Separate workspace used for tenant isolation verification",
            "developer",
            "Northstar"),
        fields("name", "Northstar Meadows", "status", "ACTIVE"));
    repo.save(
        "leads",
        other,
        null,
        fields("language", "en", "intent", "BUY"),
        fields(
            "name",
            "Separate Tenant Customer",
            "phone",
            "+919000009999",
            "email",
            "separate@example.invalid",
            "status",
            "NEW",
            "assigned_agent_id",
            otherAgent));
  }

  /** Workspace visiting hours, one project with its own, and both agents on every project. */
  private void seedVisiting(Long ws, List<Long> projects, List<Long> agents) {
    for (int day = 1; day <= 7; day++)
      db.update("INSERT INTO visit_slot_templates(workspace_id,project_id,day_of_week,start_time,end_time,"
          + "slot_minutes,capacity) VALUES (?,NULL,?,'10:00','19:00',60,3)", ws, day);
    for (int day = 1; day <= 7; day++)
      db.update("INSERT INTO visit_slot_templates(workspace_id,project_id,day_of_week,start_time,end_time,"
          + "slot_minutes,capacity) VALUES (?,?,?,?,?,60,4)", ws, projects.getFirst(), day,
          java.sql.Time.valueOf(day >= 6 ? "10:00:00" : "11:00:00"), java.sql.Time.valueOf(day >= 6 ? "19:00:00" : "18:00:00"));
    for (Long project : projects)
      for (Long agent : agents)
        db.update("INSERT INTO project_agents(workspace_id,project_id,user_id,available) VALUES (?,?,?,true)",
            ws, project, agent);
  }

  /**
   * A synthetic brochure, FAQ and price sheet for two projects, so retrieval has something to find
   * on a fresh demo. They are queued as PENDING_INDEX and sent to the knowledge service by the
   * knowledge sync once it is reachable. Fictional content only.
   */
  private void seedKnowledge(Long ws, List<Long> projects, String[] names, String[] locations) {
    for (int i = 0; i < projects.size(); i++) {
      String name = names[i], place = locations[i];
      String[][] docs = {
        {"BROCHURE", name + " brochure",
         "# " + name + "\n\n> Synthetic demonstration content for a fictional project.\n\n"
             + "## Amenities\n\n### Clubhouse\nA 10,000 sq ft clubhouse with a rooftop swimming pool, a gym and a"
             + " yoga deck.\n\n### Outdoor\nA jogging track around the central lawn, a children's play area and a"
             + " senior citizens' garden.\n\n## Specifications\nVitrified tiles in living areas, three-track aluminium"
             + " windows with mosquito mesh, granite kitchen platform with a stainless steel sink.\n\n"
             + "## Location\n" + name + " is in " + place + ", close to schools, hospitals and the main road."},
        {"FAQ", name + " FAQ",
         "# " + name + " — frequently asked questions\n\n## When is possession?\nPossession is planned for June"
             + " 2027.\n\n## Are pets allowed?\nYes, pets are welcome and there is a pet park.\n\n"
             + "## How many car parks come with a flat?\nOne covered car park with a 2 BHK and two with a 3 BHK.\n\n"
             + "## What are the site visit timings?\nThe sample flat is open every day from 10 AM to 7 PM."},
        {"PRICE_SHEET", name + " price sheet (charges)",
         "# " + name + " — charges and payment plan\n\nUnit prices are quoted live from inventory; this sheet"
             + " covers charges only.\n\n## Charges\n\n| Charge | Amount |\n|---|---|\n| Floor rise | ₹40 per sq ft"
             + " per floor above the 5th |\n| Garden-facing PLC | ₹150 per sq ft |\n| Club membership | ₹2,00,000 |\n"
             + "| Maintenance deposit | 24 months at ₹4 per sq ft |\n| GST | 5% of agreement value |\n\n"
             + "## Payment plan\n\n| Stage | Percent |\n|---|---|\n| On booking | 10% |\n| Agreement | 10% |\n"
             + "| Plinth | 15% |\n| Each slab | 5% |\n| Possession | 5% |"},
      };
      for (String[] doc : docs) {
        var saved = repo.save("property_documents", ws, null,
            fields("fileName", doc[1].toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-") + ".md",
                "storageReference", "demo://synthetic/" + projects.get(i) + "/" + doc[0].toLowerCase(Locale.ROOT),
                "storageMode", "DEMO_SYNTHETIC", "language", "en", "content", doc[2], "docType", doc[0],
                "version", 1, "processingStatus", "PENDING_INDEX", "isSynthetic", true),
            fields("project_id", projects.get(i), "title", doc[1], "status", "PUBLISHED"));
        repo.event("property_content_versions", ws, "document_id", id(saved.get("id")),
            fields("version", 1, "content", doc[2], "language", "en", "status", "PUBLISHED"));
      }
    }
  }

  private Long user(String name, String email, String hash) {
    return db.queryForObject(
        "INSERT INTO users(name,email,password_hash,enabled) VALUES (?,?,?,true) RETURNING id",
        Long.class,
        name,
        email,
        hash);
  }

  private void member(Long ws, Long user, Long role) {
    db.update(
        "INSERT INTO workspace_members(workspace_id,user_id,role_id) VALUES (?,?,?)",
        ws,
        user,
        role);
  }
}
