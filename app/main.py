import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .agent_factory import build_config_from_env, write_runtime_config
from .auth import verify_token
# from .parse_trinity import parse_trinity_files  # Removed Trinity parsing

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


def validate_kb_structure(data: Dict[str, Any]) -> Optional[str]:
    """
    Check if the uploaded JSON is at least partially valid.
    Returns an error message ONLY if none of the required sections are found.
    """
    REQUIRED_TOP_LEVEL = {
        "model_info", "performance_metrics", "confusion_matrix", "data_drift",
        "bias_report", "data_quality", "feature_importance"
    }
    
    # Rejection: If NONE of the top-level keys are found, it's likely a completely wrong file.
    found_keys = REQUIRED_TOP_LEVEL.intersection(set(data.keys()))
    if not found_keys:
        return "Completely wrong JSON structure: none of the required ML knowledge base sections were found."
    
    return None


def normalize_kb_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the JSON structure is complete by filling in missing or malformed sections
    with 'unable to parse' or placeholder values.
    """
    TEMPLATE = {
        "model_info": {"name": "unable to parse", "type": "unable to parse"},
        "performance_metrics": {
            "current": "unable to parse data from source",
            "reference": "unable to parse data from source",
            "performance_message": "data not provided",
            "severity": "info"
        },
        "confusion_matrix": {
            "labels": "unable to parse data from source",
            "derived": "unable to parse data from source"
        },
        "data_drift": {
            "drift_detected": "data not provided",
            "message": "unable to parse drift data"
        },
        "bias_report": {
            "metrics": [],
            "message": "unable to parse bias data"
        },
        "data_quality": {
            "message": "unable to parse quality data"
        },
        "feature_importance": {
            "message": "unable to parse importance data"
        }
    }

    normalized = {}
    for key, template_val in TEMPLATE.items():
        if key not in data:
            normalized[key] = template_val
        elif isinstance(template_val, dict) and not isinstance(data[key], dict):
            # If we expected an object but got something else, mark as unable to parse
            normalized[key] = {k: "unable to parse data from source" for k in template_val.keys()} if isinstance(template_val, dict) else "unable to parse data from source"
        elif isinstance(template_val, dict):
            # Deep merge/check for subkeys if it's an object
            section = data[key]
            normalized_section = {}
            for sub_k, sub_v in template_val.items():
                if sub_k not in section:
                    normalized_section[sub_k] = sub_v
                else:
                    normalized_section[sub_k] = section[sub_k]
            normalized[key] = normalized_section
        else:
            normalized[key] = data[key]
            
    # Include any other keys that were in the original data but not in template
    for key in data:
        if key not in normalized:
            normalized[key] = data[key]
            
    return normalized


class SumRequest(BaseModel):
    a: Annotated[float, Field(allow_inf_nan=False)]
    b: Annotated[float, Field(allow_inf_nan=False)]

    @field_validator("a", "b", mode="before")
    @classmethod
    def reject_bool(cls, value: Any) -> Any:
        """Reject booleans before Pydantic's numeric coercion accepts them.

        Args:
            value: The raw field value, as decoded from the request JSON.

        Returns:
            The value unchanged, if it is not a boolean.

        Raises:
            ValueError: If ``value`` is a boolean (``bool`` is a subclass of
                ``int`` in Python, so it would otherwise silently coerce to
                ``0.0``/``1.0``).
        """
        if isinstance(value, bool):
            raise ValueError("must be a number, not a boolean")
        return value


class SumResponse(BaseModel):
    result: float


class ReverseRequest(BaseModel):
    text: Annotated[str, Field(max_length=10_000)]


class ReverseResponse(BaseModel):
    reversed: str


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


async def _save_ml_knowledge_base_from_datasources(datasources: List[DatasourceFile], kb_path: Path) -> Optional[str]:
    """Helper to save the KB file from a list of datasources. Returns error message if any."""
    kb_file = next((d for d in datasources if d.name == "ml_knowledge_base.json"), None)
    if kb_file:
        try:
            kb_data = json.loads(kb_file.content)
            
            # 1. Validate if it's even the right file
            error_msg = validate_kb_structure(kb_data)
            if error_msg:
                return error_msg
            
            # 2. Normalize data (fill missing pieces with "unable to parse")
            normalized_data = normalize_kb_data(kb_data)
            
            # 3. Write to file
            with open(kb_path, "w", encoding="utf-8") as f:
                json.dump(normalized_data, f, indent=4)
            logger.info("Saved normalized ml_knowledge_base.json to %s", kb_path)
            return None
        except json.JSONDecodeError:
            return "Invalid JSON file (could not parse content)."
        except Exception as e:
            return str(e)
    return None


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


@app.post("/sum", response_model=SumResponse)
async def sum_values(request: SumRequest) -> SumResponse:
    """Add two numeric values and return their sum.

    Args:
        request: Body containing numeric fields ``a`` and ``b``.

    Returns:
        The sum of ``a`` and ``b`` as ``result``.

    Raises:
        RequestValidationError: If ``a`` or ``b`` is not numeric (FastAPI
            returns this as an HTTP 422 response automatically).
    """
    return SumResponse(result=request.a + request.b)


@app.post("/reverse", response_model=ReverseResponse)
async def reverse_text(request: ReverseRequest) -> ReverseResponse:
    """Reverse the given text.

    Args:
        request: Body containing the string field ``text`` (max 10,000
            characters).

    Returns:
        ``text`` reversed, as ``reversed``.

    Raises:
        RequestValidationError: If ``text`` is missing, not a string, or
            longer than 10,000 characters (FastAPI returns this as an HTTP
            422 response automatically).
    """
    return ReverseResponse(reversed=request.text[::-1])


@app.post("/clear-session")
async def clear_session(_auth: dict = Depends(verify_token)) -> Dict[str, str]:
    """Delete ml_knowledge_base.json when user clears session."""
    kb_path = Path(__file__).resolve().parent / "ml_knowledge_base.json"
    if kb_path.exists():
        kb_path.unlink()
        logger.info("Deleted ml_knowledge_base.json")
    return {"status": "session cleared"}


@app.post("/upload-kb")
async def upload_kb(
    request: ChatRequest,
    _auth: dict = Depends(verify_token),
) -> Dict[str, str]:
    """Dedicated endpoint to save ml_knowledge_base.json without chatting."""
    if not request.datasources:
        return {"status": "no datasources provided"}
    
    kb_path = Path(__file__).resolve().parent / "ml_knowledge_base.json"
    
    error_message = await _save_ml_knowledge_base_from_datasources(request.datasources, kb_path)
    
    if error_message:
        return {"status": "error", "message": error_message}
    elif not any(d.name == "ml_knowledge_base.json" for d in request.datasources):
        return {"status": "kb not found in datasources", "message": "No 'ml_knowledge_base.json' found in the provided datasources."}
    else:
        return {"status": "success", "message": "Knowledge base updated"}


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
    kb_path: Path = Path(__file__).resolve().parent / "ml_knowledge_base.json"

    provider = cfg["agents"]["defaults"].get("provider", "unknown")
    model = cfg["agents"]["defaults"].get("model", "unknown")

    # Parse Trinity files and write ml_knowledge_base.json when datasources provided
    ds_count = len(request.datasources) if request.datasources else 0
    logger.info("Chat request: datasources=%d", ds_count)
    # Save ml_knowledge_base.json if provided in datasources
    if request.datasources:
        error_msg = await _save_ml_knowledge_base_from_datasources(request.datasources, kb_path)
        if error_msg:
            logger.warning("KB Save/Validation error: %s", error_msg)
            return ChatResponse(
                reply=f"Error: {error_msg}. Please ensure your file follows the correct structure.",
                provider=provider,
                model=model,
                raw={"error": "validation_failed", "detail": error_msg}
            )

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
        # Strip nanobot CLI prefix and signature before showing to user
        # Handles "Using config: ..." and the "🐈 nanobot" signature
        reply_text = re.sub(
            r"(?s)Using config:.*?\n\n🐈 nanobot\r?\n",
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

