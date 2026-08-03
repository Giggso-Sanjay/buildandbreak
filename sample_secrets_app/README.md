# sample_secrets_app

Fixture app for exercising secret-scanning / detection tooling. Contains
hardcoded, clearly-fake credentials in `config.py` (AWS, Stripe, GitHub,
JWT signing key, DB password, Slack webhook) — none are real or active.

`notifier.py` is a small, working module that formats Slack messages and
HMAC-signed webhook requests using those fake credentials. It makes no
real network calls.
