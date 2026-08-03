# sample_payments_app

Fixture app for exercising secret-scanning / detection tooling. Contains
hardcoded, clearly-fake credentials in `config.py` (Stripe, AWS, Postgres,
API signing secret, SendGrid) — none are real or active.

`processor.py` is a small, working module that formats Stripe charge
requests, HMAC-signed webhook payloads, and SendGrid receipt emails using
those fake credentials. It makes no real network calls.
