"""Tests for the GET /api/v1/even-odd endpoint in app/main.py."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_even_odd_even_number() -> None:
    response = client.get("/api/v1/even-odd/4")
    assert response.status_code == 200
    assert response.json() == {"number": 4, "result": "even"}


def test_even_odd_odd_number() -> None:
    response = client.get("/api/v1/even-odd/7")
    assert response.status_code == 200
    assert response.json() == {"number": 7, "result": "odd"}


def test_even_odd_zero_is_even() -> None:
    response = client.get("/api/v1/even-odd/0")
    assert response.status_code == 200
    assert response.json() == {"number": 0, "result": "even"}


def test_even_odd_negative_number() -> None:
    response = client.get("/api/v1/even-odd/-3")
    assert response.status_code == 200
    assert response.json() == {"number": -3, "result": "odd"}


def test_even_odd_invalid_input() -> None:
    response = client.get("/api/v1/even-odd/not-a-number")
    assert response.status_code == 422


def test_even_odd_method_not_allowed() -> None:
    response = client.post("/api/v1/even-odd/4")
    assert response.status_code == 405
