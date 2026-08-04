def test_post_shorten_with_valid_url_returns_200_and_unique_code(client):
    resp = client.post("/shorten", json={"long_url": "https://example.com/a"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["code"]) == 7
    assert body["long_url"] == "https://example.com/a"


def test_two_different_shorten_calls_never_return_the_same_code(client):
    resp1 = client.post("/shorten", json={"long_url": "https://example.com/a"})
    resp2 = client.post("/shorten", json={"long_url": "https://example.com/b"})

    assert resp1.json()["code"] != resp2.json()["code"]


def test_resubmitting_an_already_shortened_url_returns_the_existing_code(client):
    first = client.post("/shorten", json={"long_url": "https://example.com/dup"})
    second = client.post("/shorten", json={"long_url": "https://example.com/dup"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["code"] == second.json()["code"]
