package com.estraos.service;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Polls the knowledge service for documents and files it is still processing. */
@Component
@ConditionalOnProperty(name = "app.knowledge.sync-enabled", havingValue = "true", matchIfMissing = true)
public class KnowledgeStatusSync {
  private final KnowledgeService knowledge;

  public KnowledgeStatusSync(KnowledgeService knowledge) {
    this.knowledge = knowledge;
  }

  @Scheduled(
      fixedDelayString = "${app.knowledge.sync-poll-ms:30000}",
      initialDelayString = "${app.knowledge.sync-poll-ms:30000}")
  public void run() {
    knowledge.syncPending();
  }
}
