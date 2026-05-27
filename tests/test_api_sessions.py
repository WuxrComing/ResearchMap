"""API integration tests for sessions."""
import os
from fastapi.testclient import TestClient
from app.main import app
from app.services.storage import init_db

os.makedirs("storage", exist_ok=True)
init_db()
client = TestClient(app)


def test_session_lifecycle():
    resp = client.post("/api/workspaces", json={
        "title": "SessTest", "description": "", "auto_generate": False
    })
    wid = resp.json()["id"]

    # List sessions (should have default)
    resp = client.get(f"/api/sessions?workspace_id={wid}")
    assert resp.status_code == 200
    initial = len(resp.json())
    assert initial >= 1

    # Create
    resp = client.post("/api/sessions", json={"workspace_id": wid, "title": "Custom"})
    assert resp.status_code == 200
    sid = resp.json()["id"]
    assert resp.json()["title"] == "Custom"

    # Update
    resp = client.put(f"/api/sessions/{sid}", json={"workspace_id": wid, "title": "Renamed"})
    assert resp.json()["title"] == "Renamed"

    # Delete
    resp = client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 200

    # Cleanup
    client.delete(f"/api/workspaces/{wid}")
