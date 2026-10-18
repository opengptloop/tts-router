"""Admin endpoints for the OpenAI-compatible API layer.

These power the in-app "API" page: the active TTS configuration (which engine
and voice serve the endpoint, speed, default format, auth mode), API key
management, and engine/voice availability. They live under ``/api`` like the
rest of the studio endpoints and are never exposed through the public ``/v1``
surface.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import audio_convert
from ..model_manager import get_manager
from ..openai_store import API_KEYS, ACTIVE_CONFIG
from ..routers.openai_api import start_engine_load

logger = logging.getLogger("tts.openai.admin")

router = APIRouter(prefix="/api/openai", tags=["openai-admin"])


class CreateKeyRequest(BaseModel):
    name: str = "Untitled key"
    rate_limit_per_min: int | None = Field(default=None, ge=0, le=100000)


class UpdateKeyRequest(BaseModel):
    name: str | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=0, le=100000)


class SaveConfigRequest(BaseModel):
    engine: str
    variant: str | None = None
    voice: str
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    response_format: str = "mp3"
    require_api_key: bool = False
    max_input_chars: int = Field(default=4096, ge=1, le=100000)


class AuthModeRequest(BaseModel):
    require_api_key: bool


def _engine_summaries() -> list[dict[str, Any]]:
    """Engine availability for the configuration UI, in a stable order."""
    manager = get_manager()
    items = []
    for engine_id, engine in manager.engines.items():
        try:
            installed = engine.installed()
        except Exception:  # pragma: no cover - defensive
            installed = False
        items.append(
            {
                "id": engine_id,
                "name": engine.name,
                "description": engine.description,
                "installed": installed,
                "loaded": manager.runtime(engine_id) is not None,
                "default_variant": engine.default_variant,
                "variants": [
                    {"id": v.get("id"), "label": v.get("label")}
                    for v in (engine.variants() or [])
                ],
            }
        )
    return items


def _voice_is_available(engine_id: str, variant: str | None, voice: str) -> bool:
    """True when ``voice`` can be used right now for the given engine.

    For Piper this means the voice ONNX files are downloaded locally; for the
    other engines the built-in voice list decides.
    """
    manager = get_manager()
    engine = manager.engines.get(engine_id)
    if engine is None:
        return False
    try:
        voices = engine.voices(variant, None)
    except Exception:  # pragma: no cover - defensive (catalog fetch failures)
        return False
    for entry in voices:
        if entry.id != voice:
            continue
        # downloaded is None -> always available (built-in voices)
        return entry.downloaded is not False
    return False


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status")
def status() -> dict:
    keys = API_KEYS.list()
    active = [key for key in keys if not key.get("revoked")]
    formats = audio_convert.formats_available()
    cfg = ACTIVE_CONFIG.get()
    return {
        "base_path": "/v1",
        "speech_endpoint": "/v1/audio/speech",
        "require_api_key": bool(cfg.get("require_api_key")),
        "auth_required": bool(cfg.get("require_api_key")),
        "keys_total": len(keys),
        "keys_active": len(active),
        "engine": cfg.get("engine"),
        "voice": cfg.get("voice"),
        "configured": bool(cfg.get("engine") and cfg.get("voice")),
        "ffmpeg_available": audio_convert.FFMPEG is not None,
        "ffmpeg_path": audio_convert.FFMPEG,
        "formats": formats,
        "supported_formats": list(formats.keys()),
    }


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


@router.get("/keys")
def list_keys() -> dict:
    return {"keys": API_KEYS.list()}


@router.post("/keys")
def create_key(payload: CreateKeyRequest) -> dict:
    record = API_KEYS.create(payload.name, payload.rate_limit_per_min)
    return {"key": record}


@router.patch("/keys/{key_id}")
def update_key(key_id: str, payload: UpdateKeyRequest) -> dict:
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = API_KEYS.update(key_id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"key": updated}


@router.delete("/keys/{key_id}")
def delete_key(key_id: str) -> dict:
    if not API_KEYS.delete(key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Active TTS configuration
# ---------------------------------------------------------------------------


@router.get("/config")
def get_config() -> dict:
    cfg = ACTIVE_CONFIG.get()
    formats = audio_convert.formats_available()
    return {
        "engine": cfg.get("engine"),
        "variant": cfg.get("variant"),
        "voice": cfg.get("voice"),
        "speed": cfg.get("speed"),
        "response_format": cfg.get("response_format"),
        "require_api_key": bool(cfg.get("require_api_key")),
        "max_input_chars": cfg.get("max_input_chars"),
        "configured": bool(cfg.get("engine") and cfg.get("voice")),
        "engines": _engine_summaries(),
        "formats_available": formats,
        "supported_formats": list(formats.keys()),
    }


@router.put("/config")
def put_config(payload: SaveConfigRequest) -> dict:
    manager = get_manager()
    engine = manager.engines.get(payload.engine)
    if engine is None:
        raise HTTPException(status_code=400, detail=f"Unknown TTS engine '{payload.engine}'.")
    if not engine.installed():
        raise HTTPException(
            status_code=400,
            detail=(
                f"{engine.name} is not installed yet. Install it on the "
                "Models & Config page first, then save the configuration."
            ),
        )
    if not _voice_is_available(payload.engine, payload.variant, payload.voice):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Voice '{payload.voice}' is not available for {engine.name}. "
                "For Piper, download the voice first (Models & Config page)."
            ),
        )
    try:
        saved = ACTIVE_CONFIG.save(
            payload.engine,
            payload.voice,
            variant=payload.variant,
            speed=payload.speed,
            response_format=payload.response_format,
            require_api_key=payload.require_api_key,
            max_input_chars=payload.max_input_chars,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Warm the engine up in the background so the very first client request
    # succeeds without waiting for a cold load.
    load_state = {"triggered": False}
    if manager.runtime(saved["engine"]) is None:
        start_engine_load(saved["engine"], saved["variant"])
        load_state = {"triggered": True}

    logger.info(
        "API config saved: engine='%s' voice='%s' format='%s' require_key=%s",
        saved["engine"],
        saved["voice"],
        saved["response_format"],
        saved["require_api_key"],
    )
    return {**saved, "engine_loading": load_state["triggered"]}


@router.patch("/config/auth")
def patch_auth_mode(payload: AuthModeRequest) -> dict:
    """Toggle 'require API key' without touching the rest of the config.

    The API is open by default — anyone who can reach the server can generate
    speech. Turning this on makes a valid key mandatory.
    """
    saved = ACTIVE_CONFIG.update_auth_mode(payload.require_api_key)
    logger.info("API auth mode: require_api_key=%s", payload.require_api_key)
    return {"require_api_key": saved["require_api_key"]}
