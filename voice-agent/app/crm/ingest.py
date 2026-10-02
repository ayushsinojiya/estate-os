"""The post-call record in the CRM's own shape: Requests.CallIngest.

The CRM rejects unknown properties (fail-on-unknown-properties), so this model is the contract:
field names, and the constraints the CRM validates, mirror the Java record. A contract test
(tests/test_contract_call_ingest.py) reads the Java source and fails if the two drift apart.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CallIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    callId: str = Field(min_length=1, max_length=80)
    voiceSessionId: str = Field(min_length=1, max_length=80)
    leadId: str
    projectId: str | None = None
    customerPhone: str | None = Field(default=None, max_length=30)
    direction: Literal["inbound", "outbound"]
    durationSeconds: float = Field(ge=0)
    language: Literal["en", "hi", "mr", "gu"] | None = None
    languagesUsed: list[str] = Field(default_factory=list, max_length=8)
    customerName: str | None = Field(default=None, max_length=160)
    budget: int | None = Field(default=None, ge=0)
    propertyType: str | None = Field(default=None, max_length=40)
    bhk: list[int] = Field(default_factory=list, max_length=8)
    location: str | None = Field(default=None, max_length=300)
    timeline: str | None = Field(default=None, max_length=80)
    intent: str | None = Field(default=None, max_length=40)
    leadScore: int | None = Field(default=None, ge=0, le=100)
    siteVisit: str | None = Field(default=None, max_length=80)
    customerSentiment: str | None = Field(default=None, max_length=40)
    summary: str | None = Field(default=None, max_length=20000)
    questionsAsked: list[str] = Field(default_factory=list, max_length=50)
    unansweredQuestions: list[str] = Field(default_factory=list, max_length=50)
    agentActions: list[str] = Field(default_factory=list, max_length=50)
    readbackOutcomes: dict[str, int] = Field(default_factory=dict)
    doNotCall: bool | None = None
    doNotCallBasis: str | None = Field(default=None, max_length=200)
    failureReason: str | None = Field(default=None, max_length=500)
    transcript: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    callType: Literal["INBOUND", "OUTBOUND_NEW_LEAD", "VISIT_REMINDER", "CALLBACK", "RE_ENGAGEMENT"] | None = None
    appointmentId: str | None = None
    callbackId: str | None = None
    visitOutcome: Literal["CONFIRMED", "RESCHEDULED", "CANCELLED", "NO_ANSWER"] | None = None
    callbackAt: datetime | None = None
    handoverRequested: bool | None = None
    handoverReason: Literal["CUSTOMER_ASKED", "NEGOTIATION", "LEGAL", "HOT_LEAD", "UNANSWERED"] | None = None
    leadTemperature: Literal["HOT", "WARM", "COLD"] | None = None
    purpose: Literal["SELF_USE", "INVESTMENT"] | None = None
    possessionPreference: Literal["READY", "UNDER_CONSTRUCTION", "ANY"] | None = None
    whatsappConsent: bool | None = None
    whatsappRequests: list[Literal["BROCHURE", "VISIT_CONFIRMATION"]] = Field(default_factory=list, max_length=4)
    citations: list[str] = Field(default_factory=list, max_length=20)
    promptVersion: str | None = Field(default=None, max_length=40)

    def payload(self) -> dict[str, Any]:
        """JSON for POST /api/v1/calls/ingest: unset optionals are left out entirely."""
        data = self.model_dump(mode="json", exclude_none=True)
        return data
