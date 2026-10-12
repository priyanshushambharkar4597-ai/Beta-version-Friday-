"""Unit tests for Friday's FastAPI application server."""

import pytest
from fastapi.testclient import TestClient
from friday.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_server_status_endpoint(client: TestClient):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "Intel Core i5-12450H" in data["host_cpu"]
    assert "0% (Enforced)" in data["gpu_utilization_policy"]
    assert data["registered_tools_count"] >= 7


def test_server_tools_list_endpoint(client: TestClient):
    response = client.get("/api/tools")
    assert response.status_code == 200
    tools = response.json()
    names = [t["name"] for t in tools]
    assert "read_file" in names
    assert "bash_execute" in names
    assert "remember" in names


def test_server_remember_and_vault(client: TestClient):
    res = client.post(
        "/api/remember",
        json={
            "title": "API Test Note",
            "content": "Testing note storage via FastAPI endpoint [[Docs]].",
            "category": "api_test",
            "tags": ["test"],
            "links": ["Docs"],
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "saved"
    assert res.json()["title"] == "API Test Note"

    # Verify visible in vault listing
    vault_res = client.get("/api/vault")
    assert vault_res.status_code == 200
    assert "API Test Note" in vault_res.json()["notes"]
