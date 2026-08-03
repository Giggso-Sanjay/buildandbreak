# sample_secrets_app

Fixture app for exercising secret-scanning / detection tooling. `config.py`
loads credentials (AWS, Stripe, GitHub, JWT signing key, DB password, Slack
webhook) from environment variables — nothing is hardcoded in source. Copy
`env.example` to `.env` and fill in values to see populated output;
it also runs fine with the defaults empty.

`notifier.py` is a small, working module that formats Slack messages and
HMAC-signed webhook requests using those credentials. It makes no real
network calls.
