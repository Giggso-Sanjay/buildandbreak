"""Small notification-formatting app used as a secret-scanner test fixture.

Builds outbound payloads (Slack message, signed webhook headers) using the
credentials in config.py. Network calls are mocked/local-only — this module
never actually reaches out to AWS, Stripe, GitHub, or Slack.
"""

import hashlib
import hmac
import json

import config


def sign_payload(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(config.JWT_SIGNING_SECRET.encode(), body, hashlib.sha256).hexdigest()


def build_slack_message(text: str) -> dict:
    return {
        "webhook_url": config.SLACK_WEBHOOK_URL,
        "payload": {"text": text},
    }


def build_signed_request(event: str, data: dict) -> dict:
    payload = {"event": event, "data": data}
    return {
        "payload": payload,
        "signature": sign_payload(payload),
        "auth_headers": {
            "X-Github-Token": config.GITHUB_TOKEN,
            "X-Stripe-Key": config.STRIPE_SECRET_KEY,
        },
    }


if __name__ == "__main__":
    msg = build_slack_message("Deployment finished")
    print(json.dumps(msg, indent=2))

    signed = build_signed_request("deploy.completed", {"env": "staging"})
    print(json.dumps(signed, indent=2))
