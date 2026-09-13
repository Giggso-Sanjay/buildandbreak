"""Tests for the GET /api/v1/status endpoint in app/main.py."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_status() -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "buildandbreak",
        "version": app.version,
    }
