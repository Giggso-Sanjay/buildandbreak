import os
from functools import lru_cache

from dotenv import load_dotenv


ENV_FILE_CANDIDATES = (
    "config.env",
    "config.env.example",
)


def _load_first_env_file() -> None:
    """
    Load the first existing env file from known candidates.
    This keeps local and Docker behavior the same.
    """
    for path in ENV_FILE_CANDIDATES:
        if os.path.exists(path):
            load_dotenv(dotenv_path=path, override=False)
            return
    # Fallback: load from default .env in cwd if present
    load_dotenv(override=False)


_load_first_env_file()


class Settings:
    @property
    def nanobot_default_provider(self) -> str:
        return os.getenv("NANOBOT_DEFAULT_PROVIDER", "ollama").lower()

    @property
    def nanobot_workspace(self) -> str:
        return os.getenv("NANOBOT_WORKSPACE", "/app/workspace")

    # Ollama
    @property
    def ollama_enabled(self) -> bool:
        return os.getenv("OLLAMA_ENABLED", "true").lower() == "true"

    @property
    def ollama_api_base(self) -> str:
        return os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

    @property
    def ollama_model(self) -> str:
        return os.getenv("OLLAMA_MODEL", "llama3.2")

    # OpenAI
    @property
    def openai_enabled(self) -> bool:
        return os.getenv("OPENAI_ENABLED", "false").lower() == "true"

    @property
    def openai_api_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @property
    def openai_model(self) -> str:
        return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    # Gemini
    @property
    def gemini_enabled(self) -> bool:
        return os.getenv("GEMINI_ENABLED", "false").lower() == "true"

    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def gemini_model(self) -> str:
        return os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()



