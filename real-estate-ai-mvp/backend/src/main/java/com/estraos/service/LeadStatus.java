package com.estraos.service;

import java.util.Map;

/**
 * The forward-only rule for lead status. Automated sources (calls, bookings, scoring) may move a
 * lead forward along the funnel but never back, so a later call cannot reopen a lead a person has
 * already qualified or handed over. People editing a lead in the CRM are not bound by it.
 */
public final class LeadStatus {
  private LeadStatus() {}

  private static final Map<String, Integer> RANK =
      Map.of(
          "NOT_INTERESTED", 0,
          "LOST", 0,
          "NEW", 1,
          "CONTACTED", 2,
          "QUALIFIED", 3,
          "VISIT_PLANNED", 4,
          "VISIT_COMPLETED", 5,
          "HANDED_OVER", 6);

  /**
   * The status to store when an automated source proposes {@code target}. A lead marked not
   * interested or lost moves forward again only on a positive action — the customer booking a visit
   * or engaging on a call — which is exactly when such a target is proposed.
   */
  public static String advance(String current, String target) {
    if (target == null || !RANK.containsKey(target)) return current;
    if (current == null || !RANK.containsKey(current)) return target;
    return RANK.get(target) > RANK.get(current) ? target : current;
  }

  public static boolean valid(String status) {
    return RANK.containsKey(status);
  }
}
