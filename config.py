"""
mock-endpoint/config.py
Azure OpenAI settings — read from environment variables only.

Required:
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_API_KEY
Optional (defaults below):
  AZURE_OPENAI_API_VERSION
  AZURE_OPENAI_DEPLOYMENT

No secret is read from disk and none is hardcoded here.
"""

import os
from functools import lru_cache

DEFAULT_API_VERSION = "2024-12-01-preview"
DEFAULT_DEPLOYMENT = "gpt-4o"


class ConfigError(RuntimeError):
    """Raised when required Azure environment variables are missing."""


class AzureConfig:
    """Resolved Azure OpenAI settings."""

    def __init__(self, endpoint: str, api_key: str, api_version: str, deployment: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.api_version = api_version
        self.deployment = deployment

    @property
    def chat_completions_url(self) -> str:
        return (
            f"{self.endpoint}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )

    def __repr__(self) -> str:  # never leak the key in logs or tracebacks
        return (
            f"AzureConfig(endpoint={self.endpoint!r}, deployment={self.deployment!r}, "
            f"api_version={self.api_version!r}, api_key=***redacted***)"
        )


@lru_cache(maxsize=1)
def get_azure_config() -> AzureConfig:
    """Resolve Azure settings once per process. Raises ConfigError if incomplete."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", DEFAULT_DEPLOYMENT)

    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_ENDPOINT", endpoint),
            ("AZURE_OPENAI_API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")

    return AzureConfig(endpoint, api_key, api_version, deployment)
