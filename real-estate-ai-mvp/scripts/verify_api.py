"""Exercise a running, disposable EstraOS demo installation.

Creates clearly named verification records, never deletes data, and exits nonzero
on any failed invariant. Set API_URL and DEMO_PASSWORD in the process environment.
Do not run against production. Uses only the Python standard library.
"""
import json
import os
import sys
import secrets
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ.get("API_URL", "http://localhost:8080/api/v1").rstrip("/")
PASSWORD = os.environ.get("DEMO_PASSWORD")
TOKEN = None
WORKSPACE = None
CHECKS = []


def request(method, path, data=None, expected=200, token=None, workspace=None):
    headers = {"Accept": "application/json"}
    bearer = TOKEN if token is None else token
    tenant = WORKSPACE if workspace is None else workspace
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    if tenant:
        headers["X-Workspace-Id"] = tenant
    raw = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        raw = json.dumps(data).encode()
    req = Request(BASE + path, data=raw, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            status, body = response.status, response.read()
    except HTTPError as error:
        status, body = error.code, error.read()
    valid = [expected] if isinstance(expected, int) else expected
    if status not in valid:
        raise AssertionError(f"{method} {path}: expected {valid}, got {status}: {body[:500].decode()}")
    return json.loads(body) if body else {}


def check(name, condition=True):
    if not condition:
        raise AssertionError(name)
    CHECKS.append(name)
    print("PASS " + name, flush=True)


def items(value):
    return value["items"] if isinstance(value, dict) else value


def main():
    global TOKEN, WORKSPACE
    if not PASSWORD:
        raise SystemExit("DEMO_PASSWORD is required; use a disposable demo installation.")
    suffix = secrets.token_hex(5)
    request("GET", "/projects", token="", workspace="", expected=401)
    check("anonymous requests rejected")
    request("POST", "/auth/login", {"email": "admin@estraos.demo", "password": secrets.token_hex(24)}, token="", workspace="", expected=401)
    login = request("POST", "/auth/login", {"email": "admin@estraos.demo", "password": PASSWORD}, token="", workspace="")
    TOKEN = login["token"]
    WORKSPACE = login["workspaces"][0]["id"]
    request("GET", "/auth/me")
    check("login and current-user endpoint")
    request("GET", "/projects", workspace="9223372036854775807", expected=[403, 404])
    check("unrelated workspace rejected")
    dashboard = request("GET", "/dashboard")
    check("dashboard explicitly marks demo data", dashboard.get("demo") is True)
    request("POST", "/projects", {"name": ""}, expected=400)
    check("project input validation")
    project_payload = {"name": "Verification " + suffix, "description": "Disposable acceptance test", "location": "Ahmedabad", "developer": "Demo developer", "possessionDate": "2028-06-01", "amenities": "Garden, gym", "status": "ACTIVE"}
    project = request("POST", "/projects", project_payload, expected=[200, 201])
    pid = project["id"]
    check("project ID is a database-generated positive numeric identity", isinstance(pid, str) and pid.isdecimal() and int(pid) > 0)
    check("project create and read", request("GET", "/projects/" + pid)["name"] == project_payload["name"])
    if len(login["workspaces"]) > 1:
        foreign_workspace = next(w["id"] for w in login["workspaces"] if w["id"] != WORKSPACE)
        foreign_projects = items(request("GET", "/projects", workspace=foreign_workspace))
        foreign_project = foreign_projects[0]["id"]
        request("GET", "/projects/" + foreign_project, expected=404)
        request("PUT", "/projects/" + foreign_project, project_payload, expected=404)
        check("actual second-tenant resources rejected under current workspace")
    building = request("POST", f"/projects/{pid}/buildings", {"name": "Tower A"}, expected=[200, 201])
    unit_payload = {"projectId": pid, "buildingId": building["id"], "unitNumber": "A101", "bhk": 2, "area": 1250, "floor": 1, "facing": "EAST", "price": 7500000, "status": "AVAILABLE", "propertyType": "APARTMENT"}
    unit = request("POST", "/units", unit_payload, expected=[200, 201])
    uid = unit["id"]
    if len(login["workspaces"]) > 1:
        request("POST", "/units", {**unit_payload, "projectId": foreign_project}, expected=[400, 404])
        check("cross-workspace related project rejected")
    request("POST", "/units", unit_payload, expected=409)
    check("unit creation and duplicate protection")
    phone = "+91" + str(int(suffix, 16))[-10:].zfill(10)
    lead_payload = {"name": "Verification buyer " + suffix, "phone": phone, "email": suffix + "@example.test", "language": "en", "intent": "BUY", "budgetMin": 5000000, "budgetMax": 9000000, "location": "Ahmedabad", "propertyType": "APARTMENT", "bhk": 2, "areaMin": 1000, "areaMax": 1500, "status": "NEW", "source": "WEBSITE", "urgency": "HIGH", "tags": "verification", "notes": "Prefers a garden"}
    lead = request("POST", "/leads", lead_payload, expected=[200, 201])
    lid = lead["id"]
    request("POST", "/leads", lead_payload, expected=409)
    lead_payload["status"] = "QUALIFIED"
    request("PUT", "/leads/" + lid, lead_payload)
    request("POST", f"/leads/{lid}/notes", {"text": "Visit requested"}, expected=[200, 201])
    check("lead creation, duplicate detection, update and note")
    doc = request("POST", "/documents", {"projectId": pid, "title": "Verification brochure", "fileName": "brochure.pdf", "storageReference": "demo/brochure.pdf", "language": "en", "pageReference": "1", "content": "The project includes a garden and gym."}, expected=[200, 201])
    did = doc["id"]
    request("PUT", f"/documents/{did}/content", {"content": "The project includes a garden, gym and walking path.", "language": "en", "pageReference": "1"})
    request("POST", f"/documents/{did}/publish", {})
    request("GET", f"/documents/{did}/versions")
    request("GET", f"/documents/{did}/processing-status")
    check("document register, edit, publish and history")
    call = request("POST", "/calls", {"leadId": lid}, expected=[200, 201, 202])
    request("POST", f"/calls/{call['id']}/refresh", {})
    request("GET", f"/calls/{call['id']}")
    check("demo voice adapter and call detail")
    recommended = request("POST", "/recommendations/search", {"leadId": lid, "projectId": pid, "language": "en", "query": "Amenities"})
    check("recommendations include matching available unit", any(r["unit"]["id"] == uid for r in recommended["items"]))
    request("POST", f"/leads/{lid}/recommendations", {"unitIds": [uid]}, expected=[200, 201])
    members = items(request("GET", "/members"))
    agent = next(m for m in members if m["role"] == "REAL_ESTATE_AGENT")
    scheduled = (datetime.now(timezone.utc) + timedelta(days=30, minutes=int(suffix[:4], 16))).replace(second=0, microsecond=0).isoformat()
    visit_payload = {"leadId": lid, "projectId": pid, "unitId": uid, "agentId": agent["id"], "scheduledAt": scheduled, "durationMinutes": 60, "status": "CONFIRMED", "notes": "Verification appointment"}
    visit = request("POST", "/site-visits", visit_payload, expected=[200, 201])
    request("POST", "/site-visits", visit_payload, expected=409)
    check("visit booking and overlap rejection")
    handover = request("POST", "/handovers", {"leadId": lid, "agentId": agent["id"], "projectId": pid, "unitId": uid, "appointmentId": visit["id"], "notes": "Agent handles all subsequent buying and legal work.", "questions": "Ask about possession.", "status": "ASSIGNED"}, expected=[200, 201])
    request("GET", f"/handovers/{handover['id']}")
    check("handover with visit and agent assignment")
    request("PUT", f"/site-visits/{visit['id']}", {**visit_payload, "status": "CANCELLED"})
    replacement_visit = request("POST", "/site-visits", visit_payload, expected=[200, 201])
    check("cancelling a visit releases its time slot", replacement_visit["id"] != visit["id"])
    unit_payload["status"] = "SOLD"
    request("PUT", "/units/" + uid, unit_payload)
    recommended = request("POST", "/recommendations/search", {"leadId": lid, "projectId": pid})
    check("sold unit excluded from recommendations", all(r["unit"]["id"] != uid for r in recommended["items"]))
    visit_payload["scheduledAt"] = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    request("POST", "/site-visits", visit_payload, expected=[400, 409, 422])
    check("unavailable unit rejected at booking")
    request("POST", f"/documents/{did}/unpublish", {})
    request("GET", "/notifications")
    check("notifications and audit available", len(items(request("GET", "/audit-logs"))) > 0)
    agent_login = request("POST", "/auth/login", {"email": "agent@estraos.demo", "password": PASSWORD}, token="", workspace="")
    request("POST", "/projects", project_payload, token=agent_login["token"], expected=403)
    request("GET", "/audit-logs", token=agent_login["token"], expected=403)
    check("agent role forbidden from inventory writes and audit")
    request("POST", "/auth/logout", {}, expected=[200, 204])
    request("GET", "/projects", expected=401)
    check("logout invalidates token")
    print(f"Verified {len(CHECKS)} acceptance groups.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAIL " + str(exc), file=sys.stderr)
        sys.exit(1)
