package com.estraos.calls;

import java.time.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * TRAI calling window for outbound calls, in Asia/Kolkata. Anything due outside the window is
 * deferred to the next resume time (09:30 by default), never dropped.
 */
@Component
public class CallingHours {
  public static final ZoneId IST = ZoneId.of("Asia/Kolkata");
  private final LocalTime start;
  private final LocalTime end;
  private final LocalTime resume;

  public CallingHours(
      @Value("${app.calls.window-start:09:00}") String start,
      @Value("${app.calls.window-end:21:00}") String end,
      @Value("${app.calls.resume-at:09:30}") String resume) {
    this.start = LocalTime.parse(start);
    this.end = LocalTime.parse(end);
    this.resume = LocalTime.parse(resume);
    if (!this.end.isAfter(this.start) || this.resume.isBefore(this.start) || !this.resume.isBefore(this.end))
      throw new IllegalStateException("Calling window must satisfy start <= resume < end");
  }

  public boolean allows(Instant at) {
    LocalTime local = at.atZone(IST).toLocalTime();
    return !local.isBefore(start) && local.isBefore(end);
  }

  /** {@code at} itself when it is inside the window, otherwise the next resume time. */
  public Instant clamp(Instant at) {
    if (allows(at)) return at;
    ZonedDateTime local = at.atZone(IST);
    LocalDate day = local.toLocalTime().isBefore(start) ? local.toLocalDate() : local.toLocalDate().plusDays(1);
    return day.atTime(resume).atZone(IST).toInstant();
  }

  public Instant startOfDay(Instant at) {
    return at.atZone(IST).toLocalDate().atStartOfDay(IST).toInstant();
  }
}
