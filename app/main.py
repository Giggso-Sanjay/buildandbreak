import logging
import subprocess
from pathlib import Path
import json
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from .agent_factory import build_config_from_env, write_runtime_config

logger = logging.getLogger("nanobot_api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Nanobot Agent API", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str
    raw: Dict[str, Any]


@app.on_event("startup")
async def on_startup() -> None:
    cfg = build_config_from_env()
    logger.info(
        "Loaded nanobot config: provider=%s model=%s",
        cfg["agents"]["defaults"].get("provider"),
        cfg["agents"]["defaults"].get("model"),
    )

    # Persist a runtime config that the `nanobot` CLI can use via -c.
    runtime_cfg_path = write_runtime_config(cfg, Path("nanobot.runtime.config.json"))

    app.state.nanobot_config = cfg
    app.state.nanobot_config_path = runtime_cfg_path


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Proxy the request into the real `nanobot` CLI:

    - Uses the env-patched config written at startup.
    - Calls: nanobot agent -c <runtime_config> -m "<message>" --no-markdown
    """
    cfg = app.state.nanobot_config
    cfg_path: Path = app.state.nanobot_config_path

    provider = cfg["agents"]["defaults"].get("provider", "unknown")
    model = cfg["agents"]["defaults"].get("model", "unknown")

    try:
        completed = subprocess.run(
            [
                "nanobot",
                "agent",
                "-c",
                str(cfg_path),
                "-m",
                request.message,
                "--no-markdown",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        # Hard failure invoking nanobot CLI
        reply_text = f"[nanobot error] Failed to invoke CLI: {exc}"
        raw: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "error": str(exc),
            "phase": "invoke_cli",
        }
        return ChatResponse(
            reply=reply_text,
            provider=provider,
            model=model,
            raw=raw,
        )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        reply_text = "[nanobot error] CLI returned non-zero exit code"
    else:
        reply_text = stdout or "[nanobot] (no output)"

    raw: Dict[str, Any] = {
        "provider": provider,
        "model": model,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "config_path": str(cfg_path),
    }

    response= ChatResponse(
        reply=reply_text,
        provider=provider,
        model=model,
        raw=raw,
    )
    
    with open("response.json", "w") as f:
        json.dump(response.model_dump(), f)
     
    return response

