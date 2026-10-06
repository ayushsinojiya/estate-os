package com.estraos.service;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Brings Projects & inventory in step with the files in File management, every couple of minutes. */
@Component
@ConditionalOnProperty(name = "app.knowledge.import-enabled", havingValue = "true", matchIfMissing = true)
public class KnowledgeInventorySync {
  private final KnowledgeInventoryImport importer;

  public KnowledgeInventorySync(KnowledgeInventoryImport importer) {
    this.importer = importer;
  }

  @Scheduled(
      fixedDelayString = "${app.knowledge.import-poll-ms:120000}",
      initialDelayString = "${app.knowledge.import-poll-ms:120000}")
  public void run() {
    importer.syncAll();
  }
}
