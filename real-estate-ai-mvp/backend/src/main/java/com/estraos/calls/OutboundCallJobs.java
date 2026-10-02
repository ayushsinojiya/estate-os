package com.estraos.calls;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Timers for the outbound call scheduler. Disabled in tests, which call the scheduler directly. */
@Component
@ConditionalOnProperty(name = "app.calls.scheduler-enabled", havingValue = "true", matchIfMissing = true)
public class OutboundCallJobs {
  private final OutboundCallScheduler scheduler;

  public OutboundCallJobs(OutboundCallScheduler scheduler) {
    this.scheduler = scheduler;
  }

  @Scheduled(fixedDelayString = "${app.calls.poll-ms:60000}", initialDelayString = "${app.calls.poll-ms:60000}")
  public void dispatch() {
    scheduler.dispatchDue();
  }

  @Scheduled(fixedDelayString = "${app.calls.reengage-scan-ms:3600000}", initialDelayString = "${app.calls.reengage-scan-ms:3600000}")
  public void reengage() {
    scheduler.scheduleReengagement();
  }
}
