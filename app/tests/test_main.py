"""Tests for the POST /sum and POST /reverse endpoints in app/main.py."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_sum_integers():
    response = client.post("/sum", json={"a": 2, "b": 3})
    assert response.status_code == 200
    assert response.json() == {"result": 5}


def test_sum_floats():
    response = client.post("/sum", json={"a": 2.5, "b": 3.25})
    assert response.status_code == 200
    assert response.json() == {"result": 5.75}


def test_sum_negative_numbers():
    response = client.post("/sum", json={"a": -10, "b": 4})
    assert response.status_code == 200
    assert response.json() == {"result": -6}


def test_sum_rejects_non_numeric_input():
    response = client.post("/sum", json={"a": "not-a-number", "b": 3})
    assert response.status_code == 422


def test_sum_rejects_infinity():
    response = client.post("/sum", json={"a": "inf", "b": 1})
    assert response.status_code == 422


def test_sum_rejects_nan():
    response = client.post("/sum", json={"a": "nan", "b": 1})
    assert response.status_code == 422


def test_sum_rejects_boolean():
    response = client.post("/sum", json={"a": True, "b": 1})
    assert response.status_code == 422


def test_sum_rejects_missing_field():
    response = client.post("/sum", json={"a": 1})
    assert response.status_code == 422


def test_reverse_text() -> None:
    response = client.post("/reverse", json={"text": "hello"})
    assert response.status_code == 200
    assert response.json() == {"reversed": "olleh"}


def test_reverse_empty_string() -> None:
    response = client.post("/reverse", json={"text": ""})
    assert response.status_code == 200
    assert response.json() == {"reversed": ""}


def test_reverse_palindrome() -> None:
    response = client.post("/reverse", json={"text": "racecar"})
    assert response.status_code == 200
    assert response.json() == {"reversed": "racecar"}


def test_reverse_rejects_missing_field() -> None:
    response = client.post("/reverse", json={})
    assert response.status_code == 422


def test_reverse_rejects_non_string_input() -> None:
    response = client.post("/reverse", json={"text": 123})
    assert response.status_code == 422
