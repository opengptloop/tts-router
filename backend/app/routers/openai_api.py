"""OpenAI-compatible speech endpoint.

One base URL, one job: clients POST to ``/v1/audio/speech`` exactly like they
would against the OpenAI API — but the only thing a client ever needs to send
is ``input`` (plus, optionally, the ``output`` format). Which engine runs, which
voice speaks, speed and the default format are all configured once from the
in-app API page. API keys are optional: the endpoint is open unless the
administrator turns on "require API key".
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np
from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from .. import audio_convert, config
from ..engines.base import EngineError
from ..logbus import BUS
from ..model_manager import get_manager
from ..openai_store import ACTIVE_CONFIG, API_KEYS, RATE_LIMITER, RESPONSE_FORMATS

logger = logging.getLogger("tts.openai.api")

router = APIRouter(prefix="/v1", tags=["openai-compatible"])

# Engine loads can be slow (first Kokoro download), so they run on daemon
# threads; /v1 waits a bounded time and answers 503 if it is still loading.
_LOAD_WAIT_SECONDS = 90.0


# ---------------------------------------------------------------------------
# OpenAI-style error payloads
# ---------------------------------------------------------------------------


def openai_error(
    status: int,
    message: str,
    err_type: str = "invalid_request_error",
    code: str | None = None,
    param: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": message,
                "type": err_type,
                "param": param,
                "code": code,
            }
        },
    )


# ---------------------------------------------------------------------------
# Request model (extra fields ignored, like the OpenAI API)
# ---------------------------------------------------------------------------


class SpeechRequest(BaseModel):
    # The only thing a client really needs to send:
    input: str | list[str] | None = None
    # Optional audio format — "output" is the friendly alias, "response_format"
    # keeps drop-in compatibility with existing OpenAI clients.
    output: str | None = None
    response_format: str | None = None
    # Accepted for OpenAI client compatibility but IGNORED: the server
    # configuration (API page) decides engine, voice, speed and default format.
    model: str | None = None
    voice: str | None = None
    speed: float | None = None


# ---------------------------------------------------------------------------
# Authentication — API keys are OPTIONAL
# ---------------------------------------------------------------------------


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    return token or (request.headers.get("api-key") or "").strip()


def authenticate(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """Return (key_record, error_response).

    Open mode (``require_api_key`` false): anyone can call the endpoint. A key
    is optional — when a valid one is presented it still gets usage stats and
    rate limits, otherwise the request simply proceeds anonymously.
    Required mode: a valid key must be presented.
    """
    required = bool(ACTIVE_CONFIG.get().get("require_api_key"))
    token = _bearer_token(request)

    if token:
        record = API_KEYS.verify(token)
        if record is not None:
            return record, None
        if required:
            return None, openai_error(
                401,
                "Incorrect API key provided. Check your key on the API page of "
                "TTS Studio. You can find your API key at the API page.",
                code="invalid_api_key",
            )
        # Open mode: tolerate placeholder keys that OpenAI SDKs insist on.
        return None, None

    if required:
        return None, openai_error(
            401,
            "You didn't provide an API key. This server requires one: send it "
            "as an Authorization header using Bearer auth (e.g. 'Authorization: "
            "Bearer sk-tts-...'). Keys are managed on the API page of TTS Studio.",
            code="invalid_api_key",
        )
    return None, None


# ---------------------------------------------------------------------------
# Engine warm-up
# ---------------------------------------------------------------------------


def start_engine_load(engine_id: str, variant: str | None) -> threading.Thread:
    """Kick off an engine load on a daemon thread (fire and forget)."""
    manager = get_manager()

    def _load():
        try:
            manager.load_model(engine_id, variant)
        except Exception:  # noqa: BLE001 - background best effort
            logger.exception("Background engine load failed for '%s'", engine_id)

    thread = threading.Thread(target=_load, name=f"engine-load-{engine_id}", daemon=True)
    thread.start()
    return thread


def ensure_engine_loaded(engine_id: str, variant: str | None) -> str | None:
    """Make sure the configured engine has a loaded runtime.

    Returns None when ready, or an error code: ``not_installed`` or
    ``loading``. A load that exceeds the wait window keeps running in the
    background; the client can retry.
    """
    manager = get_manager()
    if manager.runtime(engine_id) is not None:
        return None
    engine = manager.engines.get(engine_id)
    if engine is None:
        return "not_installed"
    if not engine.installed():
        return "not_installed"
    thread = start_engine_load(engine_id, variant)
    thread.join(timeout=_LOAD_WAIT_SECONDS)
    if thread.is_alive():
        logger.info(
            "Engine '%s' still loading after %.0fs; answering 503 while the "
            "load continues in the background",
            engine_id,
            _LOAD_WAIT_SECONDS,
        )
        return "loading"
    if manager.runtime(engine_id) is None:
        return "not_installed"
    return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
def api_info() -> dict:
    """Minimal info so users can verify the base URL is alive."""
    cfg = ACTIVE_CONFIG.get()
    return {
        "status": "ok",
        "service": config.APP_NAME,
        "message": (
            "OpenAI-compatible speech API. POST /v1/audio/speech with "
            "{\"input\": \"text\"} to synthesize. The TTS model, voice and "
            "defaults are configured in the TTS Studio API page."
        ),
        "auth_required": bool(cfg.get("require_api_key")),
        "endpoints": {"speech": "POST /v1/audio/speech"},
    }


@router.post("/audio/speech", response_model=None)
def create_speech(payload: SpeechRequest, request: Request):
    started = time.time()

    # -- auth + rate limit ------------------------------------------------
    key_record, auth_error = authenticate(request)
    if auth_error is not None:
        return auth_error
    if key_record is not None:
        limit = key_record.get("rate_limit_per_min")
        allowed, retry_after = RATE_LIMITER.check(key_record["id"], limit)
        if not allowed:
            return openai_error(
                429,
                f"Rate limit reached for this API key: {limit} requests per "
                f"minute. Retry after {retry_after}s.",
                err_type="rate_limit_error",
                code="rate_limit_exceeded",
            )

    # -- payload validation ------------------------------------------------
    raw_input = payload.input
    if isinstance(raw_input, list):
        text = "\n".join(str(part) for part in raw_input if str(part).strip())
    else:
        text = (raw_input or "").strip()
    if not text:
        return openai_error(
            400,
            "You must provide an 'input' parameter with the text to synthesize.",
            param="input",
            code="missing_input",
        )

    cfg = ACTIVE_CONFIG.get()
    max_chars = int(cfg.get("max_input_chars") or 4096)
    if len(text) > max_chars:
        return openai_error(
            400,
            f"Input is too long: {len(text)} characters (maximum is {max_chars}).",
            param="input",
            code="input_too_long",
        )

    # -- configuration resolution (server side, never the client) ----------
    engine_id = cfg.get("engine")
    if not engine_id:
        return openai_error(
            400,
            "No TTS model has been configured yet. The administrator needs to "
            "pick a model and voice on the TTS Studio API page.",
            param="model",
            code="model_not_configured",
        )

    voice_choice = cfg.get("voice")
    if not voice_choice:
        return openai_error(
            400,
            "No default voice is configured. The administrator needs to pick a "
            "voice on the TTS Studio API page.",
            param="voice",
            code="voice_not_configured",
        )

    speed = float(cfg.get("speed") or 1.0)
    requested_format = (payload.output or payload.response_format or "").strip().lower()
    if requested_format:
        if requested_format not in RESPONSE_FORMATS:
            return openai_error(
                400,
                f"Unknown output format '{requested_format}'. Supported formats: "
                + ", ".join(RESPONSE_FORMATS),
                param="output",
                code="format_unavailable",
            )
        fmt = requested_format
    else:
        fmt = str(cfg.get("response_format") or "mp3").lower()
        if fmt not in RESPONSE_FORMATS:
            fmt = "mp3"
    available = audio_convert.formats_available()
    if fmt not in available or not available[fmt]:
        return openai_error(
            400,
            f"Output format '{fmt}' is not available on this server (ffmpeg "
            "missing?). Supported formats: "
            + ", ".join(f for f in available if available[f]),
            param="output",
            code="format_unavailable",
        )

    # -- engine readiness (auto-load on demand) ------------------------------
    ready = ensure_engine_loaded(engine_id, cfg.get("variant"))
    if ready == "not_installed":
        return openai_error(
            400,
            f"The configured TTS model '{engine_id}' is not installed. The "
            "administrator can install it from the Models page.",
            code="model_not_ready",
        )
    if ready == "restart_required":
        return openai_error(
            503,
            "The TTS engine was installed while the server was running. The "
            "administrator needs to restart the backend once; please retry "
            "afterwards.",
            err_type="server_error",
            code="model_not_ready",
        )
    if ready == "loading":
        return openai_error(
            503,
            "The TTS model is still loading. Please retry in a few seconds.",
            err_type="server_error",
            code="model_loading",
        )

    # -- synthesis -----------------------------------------------------------
    manager = get_manager()
    options = {"speed": speed}

    BUS.append(
        "INFO",
        "tts.openai",
        f"API speech request: engine='{engine_id}' voice='{voice_choice}' "
        f"chars={len(text)} format={fmt} speed={speed}"
        + (f" key={key_record['name']}" if key_record else ""),
    )

    try:
        runtime, result = manager.generate(
            engine_id=engine_id,
            variant_id=cfg.get("variant"),
            voice_choice=voice_choice,
            text=text,
            options=options,
            progress=lambda fraction, message: None,
            cancelled=lambda: False,
        )
    except EngineError as exc:
        BUS.append("WARNING", "tts.openai", f"API speech failed: {exc}")
        if exc.code == "not_installed":
            return openai_error(
                400,
                f"The configured TTS model '{engine_id}' is unavailable: {exc}. "
                "The administrator can install and load it from the Models page.",
                code="model_not_ready",
            )
        if exc.code == "voice_not_found":
            return openai_error(
                400,
                f"The configured voice '{voice_choice}' is not available for "
                f"'{engine_id}': {exc}. The administrator can pick another "
                "voice on the API page.",
                param="voice",
                code="voice_not_found",
            )
        if exc.code == "engine_busy":
            return openai_error(
                503,
                "The synthesis engine is busy with another request. Please retry.",
                err_type="server_error",
                code="engine_busy",
            )
        return openai_error(400, str(exc), code=exc.code)
    except Exception as exc:  # noqa: BLE001 - surface a clean 500
        logger.exception("Speech generation failed")
        BUS.append("ERROR", "tts.openai", f"API speech crashed: {exc}")
        return openai_error(
            500,
            f"Speech generation failed: {exc}",
            err_type="server_error",
            code="internal_error",
        )

    # -- render + stream ------------------------------------------------------
    try:
        audio_path, media_type = audio_convert.render_audio(
            result.audio, result.sample_rate, fmt
        )
    except audio_convert.AudioFormatError as exc:
        return openai_error(400, str(exc), code=exc.code, param="output")

    elapsed = time.time() - started
    duration = np.asarray(result.audio).size / float(result.sample_rate)
    BUS.append(
        "INFO",
        "tts.openai",
        f"API speech done in {elapsed:.2f}s: {duration:.2f}s of {fmt} audio "
        f"({audio_path.stat().st_size / 1024:.0f} KiB) -> {audio_path.name}",
    )

    if key_record is not None:
        try:
            API_KEYS.record_usage(key_record["id"])
        except Exception:  # pragma: no cover - stats only
            logger.debug("Could not record key usage", exc_info=True)

    filename = f"speech_{int(time.time())}{audio_convert.EXTENSIONS[fmt]}"
    return FileResponse(
        audio_path,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Sample-Rate": str(result.sample_rate),
            "X-Model": str(engine_id),
            "X-Voice": str(voice_choice),
        },
        background=BackgroundTask(audio_convert.cleanup_paths, audio_path),
    )


# ---------------------------------------------------------------------------
# FastAPI request validation -> OpenAI-style errors (only for /v1 routes)
# ---------------------------------------------------------------------------


async def openai_validation_error_handler(request: Request, exc: RequestValidationError):
    """Convert FastAPI's 422 validation shape into OpenAI's error shape."""
    if not request.url.path.startswith("/v1"):
        from fastapi.exception_handlers import (
            request_validation_exception_handler,
        )

        return await request_validation_exception_handler(request, exc)

    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = [str(part) for part in first.get("loc", []) if part != "body"]
    param = ".".join(loc) or None
    detail = first.get("msg") or "Invalid request payload"
    message = f"Invalid request: {detail}"
    if param:
        message += f" (parameter '{param}')"
    return openai_error(
        400,
        message,
        err_type="invalid_request_error",
        param=param,
        code="invalid_request",
    )
