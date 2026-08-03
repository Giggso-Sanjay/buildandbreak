import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from notifier import build_slack_message, build_signed_request, sign_payload


def test_build_slack_message():
    msg = build_slack_message("hello")
    assert msg["payload"]["text"] == "hello"
    assert "webhook_url" in msg


def test_build_signed_request_includes_signature():
    signed = build_signed_request("test.event", {"key": "value"})
    assert signed["payload"]["event"] == "test.event"
    assert len(signed["signature"]) == 64
    assert "X-Github-Token" in signed["auth_headers"]


def test_sign_payload_is_deterministic():
    payload = {"a": 1, "b": 2}
    assert sign_payload(payload) == sign_payload(payload)
