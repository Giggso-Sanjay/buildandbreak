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
