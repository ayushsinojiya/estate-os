"""The service end to end: a call connects, Riya speaks first, admin routes need the token."""

import base64

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _settings(tmp_path, **extra):
    return Settings(provider_mode="fake", runtime_dir=tmp_path, crm_mode="mock", **extra)


def test_health_reports_engine_and_domain_state(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        health = client.get("/healthz").json()
        assert health["status"] == "ok" and health["mode"] == "fake"
        assert "real_estate" in health and "outbound" in health


def test_a_call_connects_and_riya_speaks_first(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        with client.websocket_connect("/telephony/voicelink/ws") as ws:
            ws.send_json({"event": "start", "start": {
                "call_id": "c1", "stream_id": "s1", "from": "9876543210",
                "to": "1800", "direction": "inbound"}})
            silence = base64.b64encode(b"\xff" * 160).decode()
            for _ in range(5):
                ws.send_json({"event": "media", "media": {"payload": silence}})
            message = ws.receive_json()
            # The greeting goes out before the caller says anything.
            assert message["event"] == "media" and message["stream_sid"] == "s1"
            ws.send_json({"event": "stop"})


def test_admin_routes_require_the_token(tmp_path):
    app = create_app(_settings(tmp_path, admin_api_token="secret"))
    with TestClient(app) as client:
        assert client.get("/calls/recent").status_code == 401
        assert client.get("/metrics").status_code == 401
        assert client.post("/v1/calls/outbound", json={}).status_code == 401
        ok = client.get("/calls/recent", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200
