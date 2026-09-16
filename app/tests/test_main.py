"""Tests for the GET /api/v1/sum-even-odd endpoint in app/main.py."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_sum_even_odd_even_result() -> None:
    response = client.get("/api/v1/sum-even-odd/1/3")
    assert response.status_code == 200
    assert response.json() == {"a": 1, "b": 3, "sum": 6, "result": "even"}


def test_sum_even_odd_odd_result() -> None:
    response = client.get("/api/v1/sum-even-odd/1/2")
    assert response.status_code == 200
    assert response.json() == {"a": 1, "b": 2, "sum": 3, "result": "odd"}


def test_sum_even_odd_single_value_range() -> None:
    response = client.get("/api/v1/sum-even-odd/5/5")
    assert response.status_code == 200
    assert response.json() == {"a": 5, "b": 5, "sum": 5, "result": "odd"}


def test_sum_even_odd_negative_range() -> None:
    response = client.get("/api/v1/sum-even-odd/-2/2")
    assert response.status_code == 200
    assert response.json() == {"a": -2, "b": 2, "sum": 0, "result": "even"}


def test_sum_even_odd_a_greater_than_b() -> None:
    response = client.get("/api/v1/sum-even-odd/5/1")
    assert response.status_code == 400


def test_sum_even_odd_invalid_input() -> None:
    response = client.get("/api/v1/sum-even-odd/not-a-number/5")
    assert response.status_code == 422


def test_sum_even_odd_method_not_allowed() -> None:
    response = client.post("/api/v1/sum-even-odd/1/3")
    assert response.status_code == 405
