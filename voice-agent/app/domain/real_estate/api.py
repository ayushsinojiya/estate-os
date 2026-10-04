"""The CRM's contract with the agent: start an outbound call, fetch a call's details.

Authenticated with ADMIN_API_TOKEN (the CRM's VOICE_AGENT_API_KEY). The agent serves one CRM
workspace; a request for any other workspace is refused.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from app.domain.real_estate.state import CALL_TYPES


def build_router(container: Callable[[], Any], admin: Callable[..., None]) -> APIRouter:
    router = APIRouter(dependencies=[Depends(admin)])

    def workspace(c: Any, body: dict) -> str:
        ws = str(body.get("workspaceId") or "")
        if ws != str(c.settings.crm_workspace_id):
            raise HTTPException(403, "this agent does not serve that workspace")
        return ws

    @router.post("/v1/calls/outbound")
    async def outbound(body: dict, c=Depends(container)) -> dict:
        ws = workspace(c, body)
        request_id = str(body.get("requestId") or "")
        phone = str(body.get("phone") or "")
        lead_id = str(body.get("leadId") or "")
        if not request_id or not phone or not lead_id or len(request_id) > 120:
            raise HTTPException(400, "workspaceId, leadId, phone and requestId are required")
        call_type = body.get("callType") or "OUTBOUND_NEW_LEAD"
        if call_type not in CALL_TYPES or call_type == "INBOUND":
            raise HTTPException(400, f"unsupported callType {call_type}")
        custom = {"workspaceId": ws, "leadId": lead_id, "callType": call_type,
                  "appointmentId": body.get("appointmentId"), "callbackId": body.get("callbackId"),
                  "projectId": body.get("projectId"), "language": body.get("language"),
                  "context": body.get("context") or {}}
        record = await c.dialer.submit(request_id, phone, custom)
        return {"externalId": record.request_id, "workspaceId": ws, "leadId": lead_id, "status": record.status,
                "reason": record.reason, "callType": call_type}

    @router.post("/v1/calls/details")
    async def details(body: dict, c=Depends(container)) -> dict:
        ws = workspace(c, body)
        record = c.registry.get(str(body.get("externalId") or ""))
        if record is None or str(record.custom.get("workspaceId")) != ws:
            raise HTTPException(404, "unknown call")
        d = record.details
        return {"externalId": record.request_id, "workspaceId": ws, "leadId": str(record.custom.get("leadId")),
                "status": record.status, "reason": record.reason, "callType": record.custom.get("callType"),
                "outcome": d.get("outcome"), "summary": d.get("summary"), "transcript": d.get("transcript"),
                "requirements": d.get("requirements") or {}, "leadScore": d.get("leadScore"),
                "handoverStatus": d.get("handoverStatus", "NOT_REQUESTED"),
                "callbackStatus": d.get("callbackStatus", "NOT_REQUESTED"),
                # Speech and model cost of the call (telephony excluded); see app/observability/cost.py.
                "cost": d.get("cost")}

    return router
