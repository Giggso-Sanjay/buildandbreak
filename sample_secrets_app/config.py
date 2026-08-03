"""Configuration for sample_secrets_app.

Credentials are loaded from environment variables — nothing is hardcoded
in source. Copy `env.example` to `.env` (git-ignored) and fill in values
to see the app produce populated output; it runs fine with the defaults
empty too.
"""

import os

from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
JWT_SIGNING_SECRET = os.getenv("JWT_SIGNING_SECRET", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
