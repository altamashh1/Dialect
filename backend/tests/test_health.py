from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "demo": False}


def test_health_reports_demo_mode(monkeypatch):
    """The login screen only offers one-click access when the API advertises it."""
    monkeypatch.setattr(settings, "demo_mode", True)
    assert client.get("/api/health").json()["demo"] is True
