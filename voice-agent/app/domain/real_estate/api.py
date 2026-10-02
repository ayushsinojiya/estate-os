"""The CRM's contract with the agent: start an outbound call, fetch a call's details."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException


def build_router(container: Callable[[], Any], admin: Callable[..., None]) -> APIRouter:
    router = APIRouter(dependencies=[Depends(admin)])

    @router.post("/v1/calls/outbound")
    async def outbound(body: dict, c=Depends(container)) -> dict:
        request_id = str(body.get("requestId") or "")
        phone = str(body.get("phone") or "")
        if not request_id or not phone:
            raise HTTPException(400, "requestId and phone are required")
        record = await c.dialer.submit(request_id, phone, {k: v for k, v in body.items() if k != "phone"})
        return {"externalId": record.request_id, "workspaceId": str(body.get("workspaceId")),
                "leadId": str(body.get("leadId")), "status": record.status}

    @router.post("/v1/calls/details")
    async def details(body: dict, c=Depends(container)) -> dict:
        record = c.registry.get(str(body.get("externalId") or ""))
        if record is None:
            raise HTTPException(404, "unknown call")
        return {"externalId": record.request_id, "workspaceId": str(body.get("workspaceId")),
                "status": record.status}

    return router
