"""API integration tests for workspaces."""
import os
from fastapi.testclient import TestClient
from app.main import app
from app.services.storage import init_db

os.makedirs("storage", exist_ok=True)
init_db()
client = TestClient(app)


def test_list_workspaces():
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_and_delete_workspace():
    resp = client.post("/api/workspaces", json={
        "title": "Test Topic", "description": "Test", "auto_generate": False
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Topic"
    assert data["session_count"] == 1

    resp = client.delete(f"/api/workspaces/{data['id']}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_update_workspace():
    resp = client.post("/api/workspaces", json={
        "title": "UpdateTest", "description": "orig", "auto_generate": False
    })
    wid = resp.json()["id"]

    resp = client.put(f"/api/workspaces/{wid}", json={
        "title": "Updated", "description": "new desc"
    })
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"
    assert resp.json()["description"] == "new desc"

    client.delete(f"/api/workspaces/{wid}")


def test_delete_nonexistent_workspace():
    resp = client.delete("/api/workspaces/nonexistent")
    assert resp.status_code == 404
