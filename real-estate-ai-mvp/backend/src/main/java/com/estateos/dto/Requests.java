package com.estateos.dto;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

public final class Requests {
  private Requests() {}

  public record Login(@NotBlank @Email String email, @NotBlank @Size(max = 128) String password) {}

  public record Project(
      @NotBlank @Size(max = 200) String name,
      @Size(max = 20000) String description,
      @NotBlank @Size(max = 300) String location,
      @Size(max = 200) String developer,
      LocalDate possessionDate,
      @Size(max = 5000) String amenities,
      @Size(max = 2000) String mediaUrl,
      String status) {}

  public record Unit(
      @NotNull Long projectId,
      Long buildingId,
      @NotBlank @Size(max = 60) String unitNumber,
      @NotNull @Min(0) @Max(20) Integer bhk,
      @NotNull @DecimalMin("0.01") BigDecimal area,
      Integer floor,
      @Size(max = 40) String facing,
      @NotNull @DecimalMin("0") BigDecimal price,
      String status,
      @NotBlank @Size(max = 40) String propertyType) {}

  public record Lead(
      @NotBlank @Size(max = 160) String name,
      @NotBlank @Size(max = 30) String phone,
      @Email @Size(max = 254) String email,
      String language,
      String intent,
      @DecimalMin("0") BigDecimal budgetMin,
      @DecimalMin("0") BigDecimal budgetMax,
      @Size(max = 300) String location,
      @Size(max = 40) String propertyType,
      @Min(0) @Max(20) Integer bhk,
      @DecimalMin("0") BigDecimal areaMin,
      @DecimalMin("0") BigDecimal areaMax,
      @Size(max = 100) String possessionTimeline,
      @Size(max = 100) String purpose,
      @Size(max = 40) String urgency,
      String status,
      @Size(max = 80) String source,
      Long assignedAgentId,
      @Size(max = 1000) String tags,
      @Size(max = 20000) String notes,
      Instant followUpAt) {}

  public record Document(
      @NotNull Long projectId,
      @NotBlank @Size(max = 200) String title,
      @NotBlank @Size(max = 255) String fileName,
      @NotBlank @Size(max = 2000) String storageReference,
      String language,
      @Size(max = 200) String pageReference,
      @Size(max = 500000) String content) {}

  public record Content(
      @NotNull @Size(max = 500000) String content,
      String language,
      @Size(max = 200) String pageReference) {}

  public record Visit(
      @NotNull Long leadId,
      @NotNull Long projectId,
      Long unitId,
      @NotNull Long agentId,
      @NotNull Instant scheduledAt,
      @NotNull @Min(15) @Max(240) Integer durationMinutes,
      @Size(max = 5000) String notes,
      String status,
      String confirmationStatus) {}

  public record Handover(
      @NotNull Long leadId,
      @NotNull Long agentId,
      Long projectId,
      Long unitId,
      Long appointmentId,
      @Size(max = 20000) String notes,
      @Size(max = 10000) String questions,
      String status) {}

  public record Note(@NotBlank @Size(max = 20000) String text) {}

  public record Call(@NotNull Long leadId) {}

  public record Suggestions(@NotEmpty @Size(max = 100) List<@NotNull Long> unitIds) {}

  public record Recommendation(
      Long leadId,
      Long projectId,
      @DecimalMin("0") BigDecimal budgetMin,
      @DecimalMin("0") BigDecimal budgetMax,
      String location,
      String propertyType,
      @Min(0) @Max(20) Integer bhk,
      @DecimalMin("0") BigDecimal areaMin,
      @DecimalMin("0") BigDecimal areaMax,
      @Size(max = 2000) String query,
      String language) {}

  /** Voice-agent lookup: resolve a caller's phone number to a lead, creating one on first contact. */
  public record LeadLookup(
      @NotBlank @Size(max = 30) String phone,
      @Size(max = 160) String name,
      @Size(max = 80) String source,
      @Size(max = 80) String campaign,
      @Positive Long projectId,
      String language) {}

  /**
   * Post-call record produced by the voice agent. Field names mirror the CRM's own camelCase
   * contract; the agent maps its internal snake_case record onto this shape before sending.
   */
  public record CallIngest(
      @NotBlank @Size(max = 80) String callId,
      @NotBlank @Size(max = 80) String voiceSessionId,
      @NotNull @Positive Long leadId,
      @Positive Long projectId,
      @Size(max = 30) String customerPhone,
      @NotBlank @Size(max = 20) String direction,
      @NotNull @DecimalMin("0") BigDecimal durationSeconds,
      String language,
      @Size(max = 8) List<@Size(max = 8) String> languagesUsed,
      @Size(max = 160) String customerName,
      @DecimalMin("0") BigDecimal budget,
      @Size(max = 40) String propertyType,
      @Size(max = 8) List<@NotNull @DecimalMin("0") BigDecimal> bhk,
      @Size(max = 300) String location,
      @Size(max = 80) String timeline,
      @Size(max = 40) String intent,
      @Min(0) @Max(100) Integer leadScore,
      @Size(max = 80) String siteVisit,
      @Size(max = 40) String customerSentiment,
      @Size(max = 20000) String summary,
      @Size(max = 50) List<@Size(max = 2000) String> questionsAsked,
      @Size(max = 50) List<@Size(max = 2000) String> unansweredQuestions,
      @Size(max = 50) List<@Size(max = 200) String> agentActions,
      Map<String, Integer> readbackOutcomes,
      Boolean doNotCall,
      @Size(max = 200) String doNotCallBasis,
      @Size(max = 500) String failureReason,
      @Size(max = 2000) List<Map<String, Object>> transcript) {}

  public record Building(@NotBlank @Size(max = 160) String name) {}

  public record Floor(@NotNull Long buildingId, @NotNull @Min(-10) @Max(300) Integer number) {}
}
