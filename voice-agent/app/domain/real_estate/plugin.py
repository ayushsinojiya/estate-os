"""The real-estate domain plugin: Riya, calling on behalf of a builder, with the CRM as the system
of record and the knowledge service for brochure facts."""

from __future__ import annotations

import asyncio
import difflib
import logging
import time
from typing import TYPE_CHECKING, Any

from app.crm.client import CrmError, HttpCrm
from app.crm.ingest import CallIngest
from app.crm.mock import MockCrm
from app.domain.base import CallInfo
from app.llm.base import Message
from app.outbound.registry import NO_ANSWER, OutboundRecord
from app.outbox.outbox import PermanentFailure
from app.rag.client import FakeKnowledge, HttpKnowledge

from .conversation import RealEstateConversation
from .phrases import RealEstatePhrases
from .prompt import PROMPT_VERSION, probe_prompt
from .sensitive import mentions_identity
from .timeutil import now_ist, within_calling_hours

if TYPE_CHECKING:
    from app.wiring import EngineServices

log = logging.getLogger(__name__)
INGEST = "crm_ingest"


# Spoken when neither BUILDER_NAME nor the CRM workspace gives a name.
FALLBACK_BUILDER = "XYZ Realty"


class RealEstatePlugin:
    name = "real_estate"

    def __init__(self, services: "EngineServices"):
        self.services = services
        self.settings = s = services.settings
        self.phrases = RealEstatePhrases(s.builder_name or FALLBACK_BUILDER, s.disclose_ai, s.disclose_recording)
        if s.crm_mode == "http":
            self.crm: Any = HttpCrm(s.crm_base_url, s.crm_workspace_id, s.crm_service_email, s.crm_service_password,
                                    refresh_margin_s=s.crm_token_refresh_margin_s,
                                    catalog_refresh_s=s.crm_catalog_refresh_s, timeout_s=s.crm_timeout_s)
        else:
            self.crm = MockCrm(s.crm_workspace_id)
        if s.rag_service_url:
            self.knowledge: Any = HttpKnowledge(s.rag_service_url, s.rag_voice_token, s.crm_workspace_id,
                                                s.rag_timeout_ms)
        else:
            self.knowledge = FakeKnowledge()
        self.catalog: dict[str, Any] | None = None
        self.catalog_at = 0.0
        self.last_rag_status: str | None = None
        self.crm_ok_at = 0.0
        self._refresh: asyncio.Task | None = None
        services.outbox.register(INGEST, self._deliver)
        services.dialer.may_dial = self.may_dial

    # ---------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        try:
            name = await asyncio.wait_for(self.crm.workspace_name(), 5)
            # A configured BUILDER_NAME is deliberate; only a blank one defers to the workspace name.
            if name and not self.settings.builder_name:
                # "Westhaven Realty · Demo" → "Westhaven Realty"
                self.phrases.builder_name = name.split("·")[0].strip() or FALLBACK_BUILDER
            self.crm_ok_at = time.time()
        except Exception as exc:  # noqa: BLE001 - the fallback name keeps the agent usable
            log.warning("CRM not reachable at start (%r); speaking as %s", exc, self.phrases.builder_name)
        await self.refresh_catalog()
        self._refresh = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        if self._refresh:
            self._refresh.cancel()
        await self.crm.aclose()
        await self.knowledge.aclose()

    async def refresh_catalog(self) -> None:
        try:
            self.catalog = await asyncio.wait_for(self.crm.get_catalog(force=True), 10)
            self.catalog_at = time.time()
            self.crm_ok_at = time.time()
        except Exception as exc:  # noqa: BLE001 - keep the previous catalogue
            log.warning("catalogue refresh failed: %r", exc)

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(max(60, self.settings.crm_catalog_refresh_s))
            await self.refresh_catalog()

    def health(self) -> dict[str, Any]:
        age = round(time.time() - self.catalog_at) if self.catalog_at else None
        return {"prompt_version": PROMPT_VERSION, "builder": self.phrases.builder_name,
                "crm_mode": self.settings.crm_mode,
                "crm_last_ok_s": round(time.time() - self.crm_ok_at) if self.crm_ok_at else None,
                "catalog_projects": len((self.catalog or {}).get("projects", [])),
                "catalog_age_s": age,
                "catalog_fresh": age is not None and age < 2 * self.settings.crm_catalog_refresh_s,
                "rag": "http" if self.settings.rag_service_url else "fake",
                "rag_last_status": self.last_rag_status}

    # ---------------------------------------------------------------- calls

    def conversation(self, info: CallInfo) -> RealEstateConversation:
        return RealEstateConversation(self, info)

    def outbound_record(self, info: CallInfo) -> OutboundRecord | None:
        request_id = str(info.custom.get("request_id") or "")
        return self.services.registry.get(request_id) if request_id else None

    def probe_messages(self) -> list[Message]:
        return [Message("system", probe_prompt(self.phrases.builder_name)),
                Message("user", "नमस्कार, बाणेरमध्ये दोन BHK फ्लॅट बद्दल माहिती हवी आहे.")]

    def is_sensitive(self, text: str) -> bool:
        return mentions_identity(text)

    def resolve_project(self, name: str) -> dict[str, Any] | None:
        """A project the caller named, matched against the catalogue's names, aliases and ids."""
        projects = (self.catalog or {}).get("projects", [])
        wanted = name.strip().lower()
        for project in projects:
            if wanted == str(project["id"]) or wanted == project["name"].lower() or wanted in project.get("aliases", []):
                return project
        for project in projects:
            if wanted in project["name"].lower() or project["name"].lower() in wanted:
                return project
        names = {project["name"].lower(): project for project in projects}
        for project in projects:
            for alias in project.get("aliases", []):
                names.setdefault(alias, project)
        close = difflib.get_close_matches(wanted, list(names), n=1, cutoff=0.75)
        return names[close[0]] if close else None

    async def may_dial(self, record: OutboundRecord) -> tuple[bool, str | None]:
        """TRAI hours and the CRM's do-not-call list, checked right before every dial."""
        s = self.settings
        if not within_calling_hours(now_ist(), s.calling_hours_start, s.calling_hours_end):
            return False, "OUTSIDE_CALLING_HOURS"
        try:
            if await asyncio.wait_for(self.crm.check_dnc(record.phone), 3):
                self.services.registry.suppress(record.phone, "CRM do-not-call list")
                return False, "DO_NOT_CALL"
        except Exception as exc:  # noqa: BLE001 - compliance first: no check, no call
            log.warning("do-not-call check unavailable (%r); not dialling %s", exc, record.request_id)
            return False, "DNC_CHECK_UNAVAILABLE"
        return True, None

    async def on_outbound_update(self, record: OutboundRecord) -> None:
        """An outbound call nobody answered still goes on the record; the CRM decides on a retry."""
        if record.status != NO_ANSWER or record.details.get("noAnswerRecorded"):
            return
        custom = record.custom
        payload = {"callId": f"{record.request_id}-noanswer"[:80], "voiceSessionId": record.request_id[:80],
                   "leadId": str(custom.get("leadId")), "customerPhone": record.phone, "direction": "outbound",
                   "durationSeconds": 0, "callType": custom.get("callType") or "OUTBOUND_NEW_LEAD",
                   "failureReason": "NO_ANSWER", "summary": "The call was not answered.",
                   "promptVersion": PROMPT_VERSION}
        if custom.get("appointmentId"):
            payload["appointmentId"] = str(custom["appointmentId"])
            if custom.get("callType") == "VISIT_REMINDER":
                payload["visitOutcome"] = "NO_ANSWER"
        self.services.registry.update(record.request_id, details={"noAnswerRecorded": True})
        self.enqueue_ingest(payload)

    # ---------------------------------------------------------------- delivery to the CRM

    def enqueue_ingest(self, payload: dict[str, Any]) -> None:
        self.services.outbox.enqueue(INGEST, payload["callId"], payload)
        self.services.metrics.inc("ingest_enqueued")

    async def _deliver(self, payload: dict[str, Any]) -> None:
        record = dict(payload)
        if not record.get("leadId"):
            # The caller lookup failed during the call (CRM down); resolve the lead now.
            lead = await self.crm.find_or_create_lead(record.get("customerPhone") or "", record.get("language"))
            record["leadId"] = str(lead["id"])
        try:
            body = CallIngest.model_validate(record).payload()
        except ValueError as exc:
            raise PermanentFailure(f"call record does not match the CRM contract: {exc}") from exc
        try:
            await self.crm.ingest_call(body)
        except CrmError as exc:
            if exc.status in (400, 404, 409, 422):
                raise PermanentFailure(f"CRM rejected the call record: {exc}") from exc
            raise
        self.crm_ok_at = time.time()
        self.services.metrics.inc("ingest_delivered")
