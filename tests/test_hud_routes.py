"""Unit tests for Jarvis HUD HTML routes and WebSocket communication."""

import pytest
from fastapi.testclient import TestClient
from friday.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_hud_html_route(client: TestClient):
    response = client.get("/hud")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "FRIDAY" in html
    assert "waveformCanvas" in html
    assert "securityModal" in html


def test_hud_websocket_telemetry(client: TestClient):
    with client.websocket_connect("/api/ws") as websocket:
        # Send security response action
        websocket.send_json({
            "action": "SECURITY_RESPONSE",
            "id": "test_req_1",
            "approved": True,
        })
        # Connection remains alive cleanly
