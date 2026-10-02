package com.estraos.calls;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.estraos.service.LeadStatus;
import java.time.*;
import org.junit.jupiter.api.Test;

class CallRulesTest {
  private final CallingHours hours = new CallingHours("09:00", "21:00", "09:30");
  private static final ZoneId IST = CallingHours.IST;

  private static Instant ist(int day, int hour, int minute) {
    return LocalDate.of(2026, 10, day).atTime(hour, minute).atZone(IST).toInstant();
  }

  @Test
  void theTraiWindowIsNineToNineIst() {
    assertThat(hours.allows(ist(5, 9, 0))).isTrue();
    assertThat(hours.allows(ist(5, 20, 59))).isTrue();
    assertThat(hours.allows(ist(5, 21, 0))).isFalse();
    assertThat(hours.allows(ist(5, 8, 59))).isFalse();
  }

  @Test
  void callsOutsideTheWindowMoveToTheNext930() {
    assertThat(hours.clamp(ist(5, 6, 0))).isEqualTo(ist(5, 9, 30));
    assertThat(hours.clamp(ist(5, 22, 30))).isEqualTo(ist(6, 9, 30));
    assertThat(hours.clamp(ist(5, 23, 59))).isEqualTo(ist(6, 9, 30));
    assertThat(hours.clamp(ist(5, 14, 0))).isEqualTo(ist(5, 14, 0));
    // 03:00 UTC is 08:30 IST: same IST day, not the next.
    assertThat(hours.clamp(Instant.parse("2026-10-05T03:00:00Z"))).isEqualTo(ist(5, 9, 30));
  }

  @Test
  void anInconsistentWindowIsRejectedAtStartup() {
    assertThatThrownBy(() -> new CallingHours("21:00", "09:00", "09:30")).isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> new CallingHours("09:00", "21:00", "08:00")).isInstanceOf(IllegalStateException.class);
  }

  @Test
  void spokenTimesAreIst() {
    assertThat(CallScheduleService.spokenTime(ist(10, 11, 0))).isEqualTo("Saturday 11 AM");
    assertThat(CallScheduleService.spokenTime(ist(10, 16, 30))).isEqualTo("Saturday 4:30 PM");
    assertThat(CallScheduleService.spokenTime(ist(11, 12, 0))).isEqualTo("Sunday 12 PM");
  }

  @Test
  void leadStatusOnlyMovesForward() {
    assertThat(LeadStatus.advance("NEW", "CONTACTED")).isEqualTo("CONTACTED");
    assertThat(LeadStatus.advance("QUALIFIED", "CONTACTED")).isEqualTo("QUALIFIED");
    assertThat(LeadStatus.advance("HANDED_OVER", "VISIT_PLANNED")).isEqualTo("HANDED_OVER");
    assertThat(LeadStatus.advance("VISIT_PLANNED", "VISIT_PLANNED")).isEqualTo("VISIT_PLANNED");
    // Booking a visit is a positive action: it brings back a lead marked not interested.
    assertThat(LeadStatus.advance("NOT_INTERESTED", "VISIT_PLANNED")).isEqualTo("VISIT_PLANNED");
    assertThat(LeadStatus.advance("QUALIFIED", "BOGUS")).isEqualTo("QUALIFIED");
  }
}
