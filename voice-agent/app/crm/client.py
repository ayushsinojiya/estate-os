"""The CRM (EstraOS) as the agent sees it: the system of record for leads, inventory, visits.

The agent logs in as the CRM's service account (POST /api/v1/auth/login), caches the token,
renews it before it expires and once more on any 401. Every call carries X-Workspace-Id, so the
CRM applies the same membership and role checks as for a person.

`CRM_MODE=mock` swaps in an in-memory CRM (app/crm/mock.py) with the same method shapes, for
offline development and tests. Payload field names are the CRM's camelCase; the post-call record
is mapped in app/crm/ingest.py and must match Requests.CallIngest exactly
(tests/test_contract_call_ingest.py fails on drift).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)


class CrmError(RuntimeError):
    def __init__(self, status: int, code: str = "", message: str = ""):
        super().__init__(f"CRM {status} {code}: {message}")
        self.status = status
        self.code = code


class Crm(Protocol):
    async def workspace_name(self) -> str | None: ...
    async def find_or_create_lead(self, phone: str, language: str | None = None, source: str = "VOICE_AGENT",
                                  project_id: str | None = None) -> dict[str, Any]: ...
    async def get_catalog(self, force: bool = False) -> dict[str, Any]: ...
    async def search_units(self, budget_inr: int | None, bhk: list[int], locality: str | None,
                           limit: int = 3) -> list[dict[str, Any]]: ...
    async def get_project(self, project_id: str) -> dict[str, Any]: ...
    async def get_availability(self, project_id: str, bhk: int | None = None) -> dict[str, Any]: ...
    async def get_price(self, project_id: str, bhk: int) -> dict[str, Any] | None: ...
    async def get_slots(self, project_id: str, from_date: str | None = None, days: int = 3) -> dict[str, Any]: ...
    async def book_visit(self, lead_id: str, project_id: str, slot_start: str, unit_id: str | None = None,
                         notes: str | None = None, language: str | None = None,
                         call_id: str | None = None) -> dict[str, Any]: ...
    async def reschedule_visit(self, appointment_id: str, slot_start: str, reason: str | None = None) -> dict[str, Any]: ...
    async def cancel_visit(self, appointment_id: str, reason: str | None = None) -> dict[str, Any]: ...
    async def confirm_visit(self, appointment_id: str) -> dict[str, Any]: ...
    async def create_callback(self, lead_id: str, due_at: datetime, reason: str | None,
                              requested_by: str = "CUSTOMER") -> dict[str, Any]: ...
    async def check_dnc(self, phone: str) -> bool: ...
    async def mark_dnc(self, phone: str, reason: str, lead_id: str | None = None) -> dict[str, Any]: ...
    async def update_lead(self, lead_id: str, patch: dict[str, Any]) -> dict[str, Any]: ...
    async def ingest_call(self, record: dict[str, Any]) -> dict[str, Any]: ...
    async def aclose(self) -> None: ...


class HttpCrm:
    def __init__(self, base_url: str, workspace_id: int, email: str, password: str, *,
                 refresh_margin_s: int = 120, catalog_refresh_s: int = 900, timeout_s: float = 2.5,
                 client: httpx.AsyncClient | None = None):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.workspace_id = str(workspace_id)
        self._email = email
        self._password = password
        self.refresh_margin_s = refresh_margin_s
        self.catalog_refresh_s = catalog_refresh_s
        self._http = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=2.0))
        self._token: str | None = None
        self._expires_at = 0.0
        self._workspaces: list[dict[str, Any]] = []
        self._login_lock = asyncio.Lock()
        self._catalog: dict[str, Any] | None = None
        self.catalog_fetched_at = 0.0

    # ---- auth

    async def _login(self) -> None:
        response = await self._http.post(f"{self.base}/auth/login",
                                         json={"email": self._email, "password": self._password})
        if response.status_code != 200:
            raise CrmError(response.status_code, "LOGIN_FAILED", "service account login failed")
        body = response.json()
        self._token = body["token"]
        self._workspaces = body.get("workspaces") or []
        try:
            expires = datetime.fromisoformat(body["expiresAt"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            expires = time.time() + 3600
        self._expires_at = expires
        log.info("CRM login ok; token valid until %s", body.get("expiresAt"))

    async def _token_value(self, force: bool = False) -> str:
        if force or self._token is None or time.time() > self._expires_at - self.refresh_margin_s:
            async with self._login_lock:
                if force or self._token is None or time.time() > self._expires_at - self.refresh_margin_s:
                    await self._login()
        return self._token  # type: ignore[return-value]

    async def request(self, method: str, path: str, *, json: Any = None,
                      params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        for attempt in (1, 2):
            token = await self._token_value(force=attempt == 2)
            response = await self._http.request(
                method, f"{self.base}{path}", json=json, params=params,
                headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": self.workspace_id,
                         **(headers or {})})
            if response.status_code == 401 and attempt == 1:
                continue  # expired or revoked session: log in again once
            if response.status_code >= 400:
                try:
                    detail = response.json()
                except ValueError:
                    detail = {}
                raise CrmError(response.status_code, str(detail.get("code", "")), str(detail.get("message", "")))
            return response.json() if response.content else {}
        raise CrmError(401, "UNAUTHORIZED", "login did not yield a usable session")

    async def workspace_name(self) -> str | None:
        await self._token_value()
        for ws in self._workspaces:
            if str(ws.get("id")) == self.workspace_id:
                return ws.get("name")
        return None

    # ---- leads

    async def find_or_create_lead(self, phone: str, language: str | None = None, source: str = "VOICE_AGENT",
                                  project_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"phone": phone, "source": source}
        if language:
            body["language"] = language
        if project_id:
            body["projectId"] = project_id
        return await self.request("POST", "/leads/find-or-create", json=body)

    async def update_lead(self, lead_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", f"/voice/leads/{lead_id}", json=patch)

    # ---- inventory

    async def get_catalog(self, force: bool = False) -> dict[str, Any]:
        if force or self._catalog is None or time.time() - self.catalog_fetched_at > self.catalog_refresh_s:
            self._catalog = await self.request("GET", "/voice/catalog")
            self.catalog_fetched_at = time.time()
        return self._catalog

    async def search_units(self, budget_inr: int | None, bhk: list[int], locality: str | None,
                           limit: int = 3) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"bhk": bhk, "limit": limit}
        if budget_inr:
            body["budgetInr"] = budget_inr
        if locality:
            body["locality"] = locality
        return (await self.request("POST", "/voice/units/search", json=body)).get("matches", [])

    async def get_project(self, project_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/voice/projects/{project_id}")

    async def get_availability(self, project_id: str, bhk: int | None = None) -> dict[str, Any]:
        return await self.request("GET", f"/voice/projects/{project_id}/availability",
                                  params={"bhk": bhk} if bhk is not None else None)

    async def get_price(self, project_id: str, bhk: int) -> dict[str, Any] | None:
        try:
            return await self.request("GET", f"/voice/projects/{project_id}/price", params={"bhk": bhk})
        except CrmError as exc:
            if exc.status == 404:
                return None  # no available unit of that size: there is no price to quote
            raise

    # ---- visits

    async def get_slots(self, project_id: str, from_date: str | None = None, days: int = 3) -> dict[str, Any]:
        params: dict[str, Any] = {"days": days}
        if from_date:
            params["from"] = from_date
        return await self.request("GET", f"/voice/projects/{project_id}/slots", params=params)

    async def book_visit(self, lead_id: str, project_id: str, slot_start: str, unit_id: str | None = None,
                         notes: str | None = None, language: str | None = None,
                         call_id: str | None = None) -> dict[str, Any]:
        body = {"leadId": lead_id, "projectId": project_id, "slotStart": slot_start, "unitId": unit_id,
                "notes": notes, "language": language, "callId": call_id}
        return await self.request("POST", "/voice/visits", json={k: v for k, v in body.items() if v is not None})

    async def reschedule_visit(self, appointment_id: str, slot_start: str, reason: str | None = None) -> dict[str, Any]:
        return await self.request("POST", f"/voice/visits/{appointment_id}/reschedule",
                                  json={"slotStart": slot_start, "reason": reason})

    async def cancel_visit(self, appointment_id: str, reason: str | None = None) -> dict[str, Any]:
        return await self.request("POST", f"/voice/visits/{appointment_id}/cancel", json={"reason": reason})

    async def confirm_visit(self, appointment_id: str) -> dict[str, Any]:
        return await self.request("POST", f"/voice/visits/{appointment_id}/confirm")

    # ---- callbacks and do-not-call

    async def create_callback(self, lead_id: str, due_at: datetime, reason: str | None,
                              requested_by: str = "CUSTOMER") -> dict[str, Any]:
        return await self.request("POST", "/voice/callbacks", json={
            "leadId": lead_id, "dueAt": due_at.isoformat().replace("+00:00", "Z"), "reason": reason,
            "requestedBy": requested_by})

    async def check_dnc(self, phone: str) -> bool:
        return bool((await self.request("GET", "/voice/dnc/check", params={"phone": phone})).get("dnc"))

    async def mark_dnc(self, phone: str, reason: str, lead_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"phone": phone, "reason": reason, "source": "VOICE_AGENT"}
        if lead_id:
            body["leadId"] = lead_id
        return await self.request("POST", "/voice/dnc", json=body)

    # ---- post-call record (called by the outbox worker, never on the call path)

    async def ingest_call(self, record: dict[str, Any]) -> dict[str, Any]:
        key = re.sub(r"[^A-Za-z0-9_:.-]", "", record["callId"])[:120] or "call"
        return await self.request("POST", "/calls/ingest", json=record, headers={"Idempotency-Key": key})

    async def aclose(self) -> None:
        await self._http.aclose()
