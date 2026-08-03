"""Small payment-processing app used as a secret-scanner test fixture.

Builds outbound payloads (Stripe charge request, signed webhook headers,
SendGrid receipt email) using the credentials in config.py. Network calls
are mocked/local-only — this module never actually reaches out to Stripe,
AWS, or SendGrid.
"""

import hashlib
import hmac
import json

import config


def sign_payload(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(config.API_SIGNING_SECRET.encode(), body, hashlib.sha256).hexdigest()


def build_charge_request(amount_cents: int, currency: str, customer_id: str) -> dict:
    payload = {"amount": amount_cents, "currency": currency, "customer": customer_id}
    return {
        "payload": payload,
        "signature": sign_payload(payload),
        "auth_headers": {
            "Authorization": f"Bearer {config.STRIPE_SECRET_KEY}",
        },
    }


def build_receipt_email(customer_email: str, amount_cents: int) -> dict:
    return {
        "api_key": config.SENDGRID_API_KEY,
        "to": customer_email,
        "subject": "Payment received",
        "body": f"We received your payment of {amount_cents / 100:.2f}.",
    }


if __name__ == "__main__":
    charge = build_charge_request(4999, "usd", "cust_fake_123")
    print(json.dumps(charge, indent=2))

    receipt = build_receipt_email("customer@example.com", 4999)
    print(json.dumps(receipt, indent=2))
