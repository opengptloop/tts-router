"""Voice catalog, Piper voice downloads, custom voice management, previews."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import config
from ..engines.base import EngineError
from ..jobs import JOBS
from ..model_manager import get_manager
from ..schemas import PreviewRequest
from ..storage import CUSTOM_VOICES

logger = logging.getLogger("tts.api.voices")

router = APIRouter(prefix="/api", tags=["voices"])

PREVIEW_TEXT = "Hello, and welcome! This is a short preview of this voice."


def _custom_entries(engine_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": voice.id,
            "name": voice.name,
            "path": str(voice.primary_path()),
            "language": voice.language,
            "reference_text": voice.reference_text,
            "created_at": voice.created_at,
        }
        for voice in CUSTOM_VOICES.list(engine_id)
    ]


@router.get("/engines/{engine_id}/voices")
def list_voices(engine_id: str, variant: str | None = None) -> dict:
    manager = get_manager()
    engine = manager.engine(engine_id)
    voices = engine.voices(variant, _custom_entries(engine_id))
    return {
        "engine": engine_id,
        "variant": variant or engine.default_variant,
        "installed": engine.installed(),
        "count": len(voices),
        "voices": [voice.as_dict() for voice in voices],
    }


# ---------------------------------------------------------------------------
# Piper specific: catalogue + downloads
# ---------------------------------------------------------------------------


@router.get("/engines/piper/catalog")
def piper_catalog(status: str | None = None) -> dict:
    from ..engines.piper_engine import CATALOG

    entries = CATALOG.get()
    items = []
    for key, entry in entries.items():
        item = dict(entry)
        item["status"] = CATALOG.local_status(key)
        items.append(item)
    if status:
        items = [item for item in items if item["status"] == status]
    return {
        "count": len(items),
        "total": len(entries),
        "items": items,
    }


@router.post("/engines/piper/catalog/refresh")
def piper_catalog_refresh() -> dict:
    from ..engines.piper_engine import CATALOG

    entries = CATALOG.get(force=True)
    return {"count": len(entries)}


@router.post("/engines/piper/voices/{voice_key}/download")
def piper_download_voice(voice_key: str) -> dict:
    manager = get_manager()
    engine = manager.require_installed("piper")

    def run(ctx):
        ctx.progress(0.02, f"Downloading {voice_key}")
        result = engine.download_voice(
            voice_key,
            progress=lambda fraction, message: ctx.progress(fraction, message),
            cancelled=ctx.is_cancelled,
        )
        ctx.progress(1.0, "Downloaded")
        return result

    job = JOBS.submit("download", f"Download Piper voice {voice_key}", run, pool="io")
    return {"job_id": job.id}


@router.delete("/engines/piper/voices/{voice_key}")
def piper_delete_voice(voice_key: str) -> dict:
    from ..engines.piper_engine import CATALOG, PiperEngine

    engine = PiperEngine()
    removed = engine.delete_voice(voice_key)
    return {"deleted": removed, "status": CATALOG.local_status(voice_key)}


# ---------------------------------------------------------------------------
# Custom voices
# ---------------------------------------------------------------------------


@router.get("/voices/custom")
def list_custom_voices(engine: str | None = None) -> dict:
    voices = CUSTOM_VOICES.list(engine)
    items = []
    for voice in voices:
        entry = voice.as_dict()
        entry["path"] = str(voice.primary_path())
        items.append(entry)
    return {"voices": items}


@router.post("/voices/custom")
async def upload_custom_voice(
    engine: str = Form(...),
    name: str = Form(...),
    language: str | None = Form(None),
    reference_text: str | None = Form(None),
    files: list[UploadFile] = File(...),
) -> dict:
    manager = get_manager()
    manager.engine(engine)  # validate engine id

    uploads = []
    for upload in files:
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"File '{upload.filename}' is empty")
        if len(content) > 512 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (max 512 MB)")
        import io

        uploads.append((upload.filename or "upload.bin", io.BytesIO(content)))

    try:
        voice = CUSTOM_VOICES.add(
            engine=engine,
            name=name,
            uploads=uploads,
            language=language or None,
            reference_text=reference_text or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    entry = voice.as_dict()
    entry["path"] = str(voice.primary_path())
    return {"voice": entry}


@router.delete("/voices/custom/{engine}/{voice_id}")
def delete_custom_voice(engine: str, voice_id: str) -> dict:
    if not CUSTOM_VOICES.delete(engine, voice_id):
        raise HTTPException(status_code=404, detail="Custom voice not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Voice previews (server side cached short samples)
# ---------------------------------------------------------------------------


def _preview_filename(engine: str, variant: str | None, voice: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", f"{engine}__{variant or 'default'}__{voice}")
    return f"{slug[:120]}.wav"


@router.post("/voices/preview")
def preview_voice(payload: PreviewRequest) -> dict:
    manager = get_manager()
    manager.require_installed(payload.engine)

    def run(ctx):
        from ..routers.generate import synth_to_file

        filename = _preview_filename(payload.engine, payload.model, payload.voice)
        target = config.PREVIEWS_DIR / filename
        if target.is_file() and target.stat().st_size > 0:
            ctx.log("Using cached preview")
            return {"audio_url": f"/api/preview-audio/{filename}", "cached": True}
        meta = synth_to_file(
            manager,
            engine_id=payload.engine,
            variant_id=payload.model,
            voice=payload.voice,
            text=PREVIEW_TEXT,
            options=payload.options,
            target=target,
            progress=lambda fraction, message: ctx.progress(fraction, message),
            cancelled=ctx.is_cancelled,
        )
        return {"audio_url": f"/api/preview-audio/{filename}", **meta}

    job = JOBS.submit(
        "preview",
        f"Preview {payload.engine} · {payload.voice}",
        run,
        pool="compute",
    )
    return {"job_id": job.id}
