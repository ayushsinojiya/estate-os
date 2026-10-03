package com.estraos.service;

import com.estraos.audit.AuditService;
import com.estraos.exception.ApiException;
import com.estraos.mapper.DtoMapper;
import com.estraos.repository.TenantRepository;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * The workspace do-not-call list. It is the source of truth: the voice agent's local suppression
 * list is only a cache of it. Numbers match on their last ten digits, the same rule the caller
 * lookup uses, so "+91 98…", "098…" and "98…" are one number.
 */
@Service
public class DncService {
  private final NamedParameterJdbcTemplate db;
  private final TenantRepository repo;
  private final AuditService audit;
  private final DtoMapper mapper;

  public DncService(
      NamedParameterJdbcTemplate db, TenantRepository repo, AuditService audit, DtoMapper mapper) {
    this.db = db;
    this.repo = repo;
    this.audit = audit;
    this.mapper = mapper;
  }

  public static String tail(String phone) {
    String digits = phone == null ? "" : phone.replaceAll("[^0-9]", "");
    return digits.length() <= 10 ? digits : digits.substring(digits.length() - 10);
  }

  public boolean listed(Long ws, String phone) {
    String tail = tail(phone);
    if (tail.length() < 7) return false;
    Boolean found =
        db.queryForObject(
            "SELECT EXISTS(SELECT 1 FROM dnc_numbers WHERE workspace_id=:ws AND phone_tail=:tail)",
            Map.of("ws", ws, "tail", tail),
            Boolean.class);
    return Boolean.TRUE.equals(found);
  }

  public Map<String, Object> check(Long ws, String phone) {
    return EstateService.fields("phone", "…" + right(tail(phone), 4), "dnc", listed(ws, phone));
  }

  private static String right(String value, int n) {
    return value.length() <= n ? value : value.substring(value.length() - n);
  }

  /**
   * Adds a number. Idempotent: listing a listed number keeps the first record. The lead, if
   * given, is marked not to be called and moves to NOT_INTERESTED.
   */
  @Transactional
  public Map<String, Object> add(
      Long ws, String phone, String reason, String source, Long leadId, Long actor) {
    String tail = tail(phone);
    if (tail.length() < 7) throw ApiException.bad("Phone must contain at least 7 digits");
    if (leadId != null) repo.get("leads", ws, leadId);
    Map<String, Object> data =
        EstateService.fields(
            "phone", phone, "reason", reason, "source", source == null ? "MANUAL" : source,
            "leadId", leadId == null ? null : leadId.toString(), "userId",
            actor == null ? null : actor.toString(), "listedAt", Instant.now().toString());
    int inserted =
        db.update(
            "INSERT INTO dnc_numbers(workspace_id,phone_tail,data) VALUES"
                + " (:ws,:tail,CAST(:data AS jsonb)) ON CONFLICT (workspace_id,phone_tail) DO NOTHING",
            Map.of("ws", ws, "tail", tail, "data", mapper.write(data)));
    // Every lead on this number is covered, not only the one named.
    var leads =
        db.queryForList(
            "SELECT id, status FROM leads WHERE workspace_id=:ws AND"
                + " right(regexp_replace(phone,'[^0-9]','','g'),10)=:tail",
            Map.of("ws", ws, "tail", tail));
    for (var lead : leads) {
      Long id = ((Number) lead.get("id")).longValue();
      db.update(
          "UPDATE leads SET status='NOT_INTERESTED', data=data||jsonb_build_object('doNotCall',true,"
              + "'doNotCallBasis',CAST(:basis AS text)), updated_at=now() WHERE workspace_id=:ws AND id=:id",
          Map.of("ws", ws, "id", id, "basis", reason == null ? "do-not-call list" : reason));
      if (!"NOT_INTERESTED".equals(lead.get("status")))
        repo.event(
            "lead_status_history", ws, "lead_id", id,
            EstateService.fields(
                "from", lead.get("status"), "to", "NOT_INTERESTED", "reason", "Do-not-call request"));
      repo.event(
          "lead_activities", ws, "lead_id", id,
          EstateService.fields(
              "action", "DO_NOT_CALL", "description", "Number added to the do-not-call list",
              "userId", actor));
      // Nothing further may be dialled for this lead.
      db.update(
          "UPDATE scheduled_calls SET status='CANCELLED', updated_at=now(),"
              + " data=data||'{\"cancelReason\":\"DO_NOT_CALL\"}' WHERE workspace_id=:ws AND"
              + " lead_id=:id AND status='SCHEDULED'",
          Map.of("ws", ws, "id", id));
    }
    if (inserted == 1) audit.record(ws, actor, "DNC_ADDED", "LEAD", leadId);
    return EstateService.fields("dnc", true, "created", inserted == 1, "leadsUpdated", leads.size());
  }
}
