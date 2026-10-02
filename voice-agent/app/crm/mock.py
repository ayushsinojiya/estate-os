"""An in-memory CRM with the real API's shapes, for CRM_MODE=mock (offline work and tests).

Two fictional Pune projects with live-looking inventory, computed visit slots in IST, leads, DNC,
callbacks and the post-call records it receives. It is a stand-in for the HTTP contract, not a
second implementation of the CRM's rules.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PROJECTS = [
    {"id": "11", "name": "Sahyadri Grove", "location": "Baner, Pune", "possessionDate": "2027-12-01",
     "reraId": "P52100054321",
     "units": {2: (8_500_000, 9_400_000, 12, 980), 3: (12_000_000, 13_800_000, 6, 1350)}},
    {"id": "12", "name": "Mula Vista", "location": "Kharadi, Pune", "possessionDate": "2026-12-01",
     "reraId": "P52100067890",
     "units": {1: (5_200_000, 5_900_000, 4, 610), 2: (7_600_000, 8_300_000, 0, 890)}},
]


def _tail(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    return digits[-10:]


class MockCrm:
    def __init__(self, workspace_id: int = 1, workspace_name: str = "Westhaven Realty · Demo"):
        self.workspace_id = str(workspace_id)
        self.name = workspace_name
        self.leads: dict[str, dict[str, Any]] = {}
        self.visits: dict[str, dict[str, Any]] = {}
        self.callbacks: dict[str, dict[str, Any]] = {}
        self.dnc: set[str] = set()
        self.ingested: list[dict[str, Any]] = []
        self.patches: list[tuple[str, dict[str, Any]]] = []
        self._ids = itertools.count(401)
        self.catalog_fetched_at = 0.0
        self.fail_ingest = 0  # tests: fail this many ingest attempts before accepting

    async def workspace_name(self) -> str | None:
        return self.name

    # ---- leads

    async def find_or_create_lead(self, phone: str, language: str | None = None, source: str = "VOICE_AGENT",
                                  project_id: str | None = None) -> dict[str, Any]:
        tail = _tail(phone)
        for lead in self.leads.values():
            if _tail(lead["phone"]) == tail:
                return {**lead, "created": False}
        lead_id = str(next(self._ids))
        lead = {"id": lead_id, "workspaceId": self.workspace_id, "name": f"Caller {tail[-4:]}", "phone": "+91" + tail,
                "status": "NEW", "language": language or "hi", "source": source, "projectId": project_id}
        self.leads[lead_id] = lead
        return {**lead, "created": True}

    async def update_lead(self, lead_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.patches.append((lead_id, patch))
        lead = self.leads.setdefault(lead_id, {"id": lead_id, "status": "NEW", "phone": ""})
        lead.update({k: v for k, v in patch.items() if v is not None and k != "status"})
        return lead

    # ---- inventory

    async def get_catalog(self, force: bool = False) -> dict[str, Any]:
        projects = []
        for p in PROJECTS:
            locality = p["location"].split(",")[0]
            projects.append({
                "id": p["id"], "name": p["name"], "aliases": [p["name"].lower(), p["name"].split()[0].lower()],
                "localityId": "loc_" + locality.lower().replace(" ", "_"), "possessionDate": p["possessionDate"],
                "reraId": p["reraId"],
                "unitTypes": [{"bhk": bhk, "carpetAreaSqft": area, "priceMinInr": lo, "priceMaxInr": hi,
                               "availableUnits": n} for bhk, (lo, hi, n, area) in p["units"].items() if n > 0]})
        localities = [{"id": "loc_" + p["location"].split(",")[0].lower(), "name": p["location"].split(",")[0],
                       "aliases": [p["location"].split(",")[0].lower()]} for p in PROJECTS]
        return {"workspaceId": self.workspace_id, "localities": localities,
                "operatingLocalityIds": [loc["id"] for loc in localities], "projects": projects}

    def _project(self, project_id: str) -> dict[str, Any]:
        for p in PROJECTS:
            if p["id"] == str(project_id):
                return p
        from app.crm.client import CrmError

        raise CrmError(404, "NOT_FOUND", "Resource not found in this workspace")

    async def search_units(self, budget_inr: int | None, bhk: list[int], locality: str | None,
                           limit: int = 3) -> list[dict[str, Any]]:
        matches = []
        for p in PROJECTS:
            if locality and locality.lower() not in p["location"].lower():
                continue
            for size, (lo, hi, n, _area) in p["units"].items():
                if n == 0 or (bhk and size not in bhk) or (budget_inr and lo > budget_inr * 1.1):
                    continue
                matches.append({"projectId": p["id"], "projectName": p["name"], "localityName": p["location"],
                                "bhk": size, "priceMinInr": lo, "priceMaxInr": hi, "availableUnits": n,
                                "possessionDate": p["possessionDate"]})
        key = (lambda m: abs(m["priceMinInr"] - budget_inr)) if budget_inr else (lambda m: m["priceMinInr"])
        return sorted(matches, key=key)[:limit]

    async def get_project(self, project_id: str) -> dict[str, Any]:
        p = self._project(project_id)
        return {"id": p["id"], "name": p["name"], "status": "ACTIVE", "localityName": p["location"],
                "possessionDate": p["possessionDate"], "reraId": p["reraId"],
                "unitTypes": [{"bhk": b, "carpetAreaSqft": a} for b, (_l, _h, n, a) in p["units"].items() if n > 0]}

    async def get_availability(self, project_id: str, bhk: int | None = None) -> dict[str, Any]:
        p = self._project(project_id)
        count = sum(n for b, (_l, _h, n, _a) in p["units"].items() if bhk is None or b == bhk)
        return {"projectId": p["id"], "bhk": bhk, "availableUnits": count,
                "asOf": datetime.now(timezone.utc).isoformat()}

    async def get_price(self, project_id: str, bhk: int) -> dict[str, Any] | None:
        p = self._project(project_id)
        unit = p["units"].get(bhk)
        if not unit or unit[2] == 0:
            return None
        return {"priceMinInr": unit[0], "priceMaxInr": unit[1], "availableUnits": unit[2], "projectId": p["id"],
                "bhk": bhk, "asOf": datetime.now(timezone.utc).isoformat()}

    # ---- visits

    @staticmethod
    def _label(at: datetime) -> str:
        local = at.astimezone(IST)
        hour = local.hour % 12 or 12
        minutes = "" if local.minute == 0 else f":{local.minute:02d}"
        return f"{local.strftime('%A')} {hour}{minutes} {'AM' if local.hour < 12 else 'PM'}"

    async def get_slots(self, project_id: str, from_date: str | None = None, days: int = 3) -> dict[str, Any]:
        p = self._project(project_id)
        start = date.fromisoformat(from_date) if from_date else datetime.now(IST).date()
        earliest = datetime.now(timezone.utc) + timedelta(hours=1)
        slots = []
        for d in range(days):
            day = start + timedelta(days=d)
            for hour in range(10, 19):
                at = datetime.combine(day, time(hour), IST).astimezone(timezone.utc)
                taken = sum(1 for v in self.visits.values()
                            if v["projectId"] == p["id"] and v["scheduledAt"] == at.isoformat() and v["status"] != "CANCELLED")
                if at < earliest or taken >= 3:
                    continue
                slots.append({"start": at.isoformat().replace("+00:00", "Z"), "end": (at + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                              "startLocal": at.astimezone(IST).isoformat(), "label": self._label(at),
                              "date": at.astimezone(IST).date().isoformat(), "capacity": 3, "remaining": 3 - taken})
        return {"projectId": p["id"], "projectName": p["name"], "timezone": "Asia/Kolkata",
                "from": start.isoformat(), "days": days, "slots": slots}

    async def book_visit(self, lead_id: str, project_id: str, slot_start: str, unit_id: str | None = None,
                         notes: str | None = None, language: str | None = None,
                         call_id: str | None = None) -> dict[str, Any]:
        p = self._project(project_id)
        at = datetime.fromisoformat(slot_start.replace("Z", "+00:00")).astimezone(timezone.utc)
        visit_id = str(next(self._ids))
        visit = {"id": visit_id, "leadId": lead_id, "projectId": p["id"], "projectName": p["name"],
                 "scheduledAt": at.isoformat(), "status": "CONFIRMED", "agentId": "7", "agentName": "Riya Desai",
                 "agentPhone": "+919800000101", "spokenTime": self._label(at), "bookedBy": "VOICE_AGENT",
                 "scheduledAtLocal": at.astimezone(IST).isoformat(), "callId": call_id}
        self.visits[visit_id] = visit
        if lead_id in self.leads:
            self.leads[lead_id]["status"] = "VISIT_PLANNED"
        return visit

    def _visit(self, appointment_id: str) -> dict[str, Any]:
        visit = self.visits.get(str(appointment_id))
        if visit is None:
            from app.crm.client import CrmError

            raise CrmError(404, "NOT_FOUND", "Resource not found in this workspace")
        return visit

    async def reschedule_visit(self, appointment_id: str, slot_start: str, reason: str | None = None) -> dict[str, Any]:
        visit = self._visit(appointment_id)
        at = datetime.fromisoformat(slot_start.replace("Z", "+00:00")).astimezone(timezone.utc)
        visit.update(scheduledAt=at.isoformat(), status="RESCHEDULED", spokenTime=self._label(at))
        return visit

    async def cancel_visit(self, appointment_id: str, reason: str | None = None) -> dict[str, Any]:
        visit = self._visit(appointment_id)
        visit.update(status="CANCELLED", cancelReason=reason)
        return visit

    async def confirm_visit(self, appointment_id: str) -> dict[str, Any]:
        visit = self._visit(appointment_id)
        visit.update(status="CONFIRMED", confirmationStatus="CONFIRMED")
        return visit

    # ---- callbacks and do-not-call

    async def create_callback(self, lead_id: str, due_at: datetime, reason: str | None,
                              requested_by: str = "CUSTOMER") -> dict[str, Any]:
        callback = {"id": str(next(self._ids)), "leadId": lead_id, "dueAt": due_at.isoformat(), "reason": reason,
                    "requestedBy": requested_by, "status": "SCHEDULED"}
        self.callbacks[callback["id"]] = callback
        return callback

    async def check_dnc(self, phone: str) -> bool:
        return _tail(phone) in self.dnc

    async def mark_dnc(self, phone: str, reason: str, lead_id: str | None = None) -> dict[str, Any]:
        created = _tail(phone) not in self.dnc
        self.dnc.add(_tail(phone))
        return {"dnc": True, "created": created}

    async def ingest_call(self, record: dict[str, Any]) -> dict[str, Any]:
        if self.fail_ingest > 0:
            self.fail_ingest -= 1
            from app.crm.client import CrmError

            raise CrmError(503, "UNAVAILABLE", "simulated outage")
        self.ingested.append(record)
        return {"id": str(uuid.uuid4()), "status": "COMPLETED", "leadId": record["leadId"]}

    async def aclose(self) -> None:
        return None
