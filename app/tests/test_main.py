"""Tests for the GET /api/v1/status endpoint in app/main.py."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_status(client: TestClient) -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "buildandbreak",
        "version": app.version,
    }


def test_status_method_not_allowed(client: TestClient) -> None:
    response = client.post("/api/v1/status")
    assert response.status_code == 405
