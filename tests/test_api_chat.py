"""API integration tests for chat."""
import os
from fastapi.testclient import TestClient
from app.main import app
from app.services.storage import init_db

os.makedirs("storage", exist_ok=True)
init_db()
client = TestClient(app)


def test_list_messages():
    resp = client.post("/api/workspaces", json={
        "title": "ChatTest", "description": "", "auto_generate": False
    })
    wid = resp.json()["id"]
    resp = client.get(f"/api/sessions?workspace_id={wid}")
    sid = resp.json()[0]["id"]

    resp = client.get(f"/api/chat?session_id={sid}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    client.delete(f"/api/workspaces/{wid}")


def test_cancel_message():
    resp = client.post("/api/workspaces", json={
        "title": "CancelTest", "description": "", "auto_generate": False
    })
    wid = resp.json()["id"]

    resp = client.post("/api/chat/cancel", json={
        "session_id": "any", "root_user_message_id": "any"
    })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    client.delete(f"/api/workspaces/{wid}")
