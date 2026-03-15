import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from .settings import get_settings

logger = logging.getLogger(__name__)


def load_base_config() -> Dict[str, Any]:
    """
    Load the base nanobot.config.json from disk.
    """
    cfg_path = Path(os.getenv("NANOBOT_CONFIG_PATH", "nanobot.config.json"))
    if not cfg_path.exists():
        raise FileNotFoundError(f"nanobot config not found at {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_config_from_env() -> Dict[str, Any]:
    """
    Take the base config and patch providers + defaults based on env.
    """
    settings = get_settings()
    cfg = load_base_config()

    # Ensure base structure
    cfg.setdefault("agents", {}).setdefault("defaults", {})
    cfg.setdefault("providers", {})

    defaults = cfg["agents"]["defaults"]
    providers = cfg["providers"]

    # Workspace
    defaults["workspace"] = settings.nanobot_workspace

    # Ollama
    if settings.ollama_enabled:
        providers.setdefault("ollama", {})
        providers["ollama"]["apiBase"] = settings.ollama_api_base

    # OpenAI
    if settings.openai_enabled and settings.openai_api_key:
        providers.setdefault("openai", {})
        providers["openai"]["apiKey"] = settings.openai_api_key

    # Gemini
    if settings.gemini_enabled and settings.gemini_api_key:
        providers.setdefault("gemini", {})
        providers["gemini"]["apiKey"] = settings.gemini_api_key

    # Default provider/model selection
    provider = settings.nanobot_default_provider
    defaults["provider"] = provider

    if provider == "ollama":
        defaults["model"] = settings.ollama_model
    elif provider == "openai":
        defaults["model"] = settings.openai_model
    elif provider == "gemini":
        defaults["model"] = settings.gemini_model
    else:
        logger.warning("Unknown NANOBOT_DEFAULT_PROVIDER=%s, falling back to ollama", provider)
        defaults["provider"] = "ollama"
        defaults["model"] = settings.ollama_model

    return cfg


def write_runtime_config(cfg: Dict[str, Any], path: Path) -> Path:
    """
    Write the assembled nanobot config to disk so the `nanobot` CLI can use it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    logger.info("Wrote runtime nanobot config to %s", path)
    return path
