import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent_factory import build_config_from_env, write_runtime_config
from .auth import verify_token
from .parse_trinity import parse_trinity_files

logger = logging.getLogger("nanobot_api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Nanobot Agent API", version="0.1.0")

# CORS for dev; prod serves FE from same origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DatasourceFile(BaseModel):
    name: str
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    datasources: Optional[List[DatasourceFile]] = None


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


@app.post("/clear-session")
async def clear_session(_auth: dict = Depends(verify_token)) -> Dict[str, str]:
    """Delete ml_knowledge_base.json when user clears session."""
    kb_path = Path(__file__).resolve().parent.parent / "ml_knowledge_base.json"
    if kb_path.exists():
        kb_path.unlink()
        logger.info("Deleted ml_knowledge_base.json")
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _auth: dict = Depends(verify_token),
) -> ChatResponse:
    """
    Proxy the request into the real `nanobot` CLI:

    - Uses the env-patched config written at startup.
    - Calls: nanobot agent -c <runtime_config> -m "<message>" --no-markdown
    """
    cfg = app.state.nanobot_config
    cfg_path: Path = app.state.nanobot_config_path
    kb_path: Path = Path(__file__).resolve().parent.parent / "ml_knowledge_base.json"

    provider = cfg["agents"]["defaults"].get("provider", "unknown")
    model = cfg["agents"]["defaults"].get("model", "unknown")

    # Parse Trinity files and write ml_knowledge_base.json when datasources provided
    ds_count = len(request.datasources) if request.datasources else 0
    logger.info("Chat request: datasources=%d", ds_count)
    if request.datasources and ds_count >= 3:
        try:
            files_data = [{"name": d.name, "content": d.content} for d in request.datasources]
            kb = parse_trinity_files(files_data)
            with open(kb_path, "w", encoding="utf-8") as f:
                json.dump(kb, f, indent=4)
            logger.info("Wrote ml_knowledge_base.json from %d datasources", ds_count)
        except Exception as e:
            logger.warning("Failed to parse datasources: %s", e)

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
            env=os.environ.copy(),
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
        err_detail = stderr or stdout or "No output captured"
        reply_text = f"[nanobot error] CLI returned non-zero exit code (exit {completed.returncode})\n\n{err_detail}"
    else:
        reply_text = stdout or "[nanobot] (no output)"
        # Strip nanobot CLI prefix before showing to user
        reply_text = re.sub(
            r"Using config:.*?\n\n🐈 nanobot\n",
            "",
            reply_text,
            count=1,
        ).strip()

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


# ─── Serve frontend (same image, AWS deployment) ─────────────────────────────
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "index.html"))

    _favicon = STATIC_DIR / "favicon.svg"
    if _favicon.exists():

        @app.get("/favicon.svg")
        async def favicon() -> FileResponse:
            return FileResponse(str(_favicon))

    @app.get("/{path:path}")
    async def serve_spa(path: str) -> FileResponse:
        return FileResponse(str(STATIC_DIR / "index.html"))

