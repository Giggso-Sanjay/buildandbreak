# sample_payments_app

Fixture app for exercising secret-scanning / detection tooling. `config.py`
loads credentials (Stripe, AWS, Postgres, API signing secret, SendGrid)
from environment variables — nothing is hardcoded in source. Copy
`env.example` to `.env` and fill in values to see populated output;
it also runs fine with the defaults empty.

`processor.py` is a small, working module that formats Stripe charge
requests, HMAC-signed webhook payloads, and SendGrid receipt emails using
those credentials. It makes no real network calls.
