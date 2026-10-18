"""Speech generation, audio serving and history endpoints."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import config
from ..jobs import JOBS
from ..model_manager import get_manager
from ..schemas import GenerateRequest
from ..storage import HISTORY, HistoryEntry

logger = logging.getLogger("tts.api.generate")

router = APIRouter(prefix="/api", tags=["generation"])


def synth_to_file(
    manager,
    engine_id: str,
    variant_id: str | None,
    voice: str,
    text: str,
    options: dict[str, Any],
    target: Path,
    progress: Callable[[float, str | None], None],
    cancelled: Callable[[], bool],
) -> dict[str, Any]:
    """Run a generation and write the audio to ``target`` (wav)."""
    runtime, result = manager.generate(
        engine_id=engine_id,
        variant_id=variant_id,
        voice_choice=voice,
        text=text,
        options=options or {},
        progress=progress,
        cancelled=cancelled,
    )
    audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
    audio = np.clip(audio, -1.0, 1.0)
    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(target), audio, result.sample_rate, subtype="PCM_16")
    duration = len(audio) / float(result.sample_rate)
    return {
        "variant": runtime.variant_id,
        "device": runtime.device,
        "sample_rate": result.sample_rate,
        "duration_s": round(duration, 3),
        "samples": int(len(audio)),
        "meta": result.meta,
    }


@router.post("/generate")
def generate(payload: GenerateRequest) -> dict:
    manager = get_manager()
    engine = manager.require_installed(payload.engine)

    engine_name = engine.name
    variant_label = payload.model or engine.default_variant

    def run(ctx):
        started = time.time()
        file_id = uuid.uuid4().hex[:12]
        filename = f"{file_id}.wav"
        target = config.OUTPUTS_DIR / filename

        ctx.progress(0.0, "Starting")
        meta = synth_to_file(
            manager,
            engine_id=payload.engine,
            variant_id=payload.model,
            voice=payload.voice,
            text=payload.text,
            options=payload.options,
            target=target,
            progress=lambda fraction, message: ctx.progress(fraction, message),
            cancelled=ctx.is_cancelled,
        )
        wall_time = time.time() - started

        voice_label = payload.voice
        if payload.voice.startswith("custom:"):
            from ..storage import CUSTOM_VOICES

            custom = CUSTOM_VOICES.get(payload.engine, payload.voice.split(":", 1)[1])
            if custom:
                voice_label = custom.name

        entry = HISTORY.add(
            HistoryEntry(
                id=file_id,
                created_at=time.time(),
                engine=payload.engine,
                model=meta["variant"],
                model_label=_variant_label(engine, meta["variant"]),
                voice=payload.voice,
                voice_label=voice_label,
                text=payload.text,
                chars=len(payload.text),
                duration_s=meta["duration_s"],
                sample_rate=meta["sample_rate"],
                wall_time_s=round(wall_time, 3),
                file=filename,
                options=payload.options or {},
            )
        )
        ctx.log(
            f"Generated {meta['duration_s']:.2f}s of audio in {wall_time:.2f}s -> {filename}"
        )
        return {
            "audio_url": f"/api/audio/{filename}",
            "history": entry,
            **meta,
            "wall_time_s": round(wall_time, 3),
            "engine": payload.engine,
            "engine_name": engine_name,
            "voice": payload.voice,
            "voice_label": voice_label,
            "text": payload.text,
        }

    job = JOBS.submit(
        "generate",
        f"{engine_name} · {variant_label} · {payload.voice}",
        run,
        pool="compute",
    )
    return {"job_id": job.id}


def _variant_label(engine, variant_id: str) -> str:
    for variant in engine.variants():
        if variant["id"] == variant_id:
            return variant["label"]
    return variant_id


# ---------------------------------------------------------------------------
# Audio files
# ---------------------------------------------------------------------------


def _safe_audio(root: Path, filename: str) -> Path:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (root / filename).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")
    return path


@router.get("/audio/{filename}")
def get_audio(filename: str) -> FileResponse:
    path = _safe_audio(config.OUTPUTS_DIR, filename)
    return FileResponse(path, media_type="audio/wav", filename=filename)


@router.get("/preview-audio/{filename}")
def get_preview_audio(filename: str) -> FileResponse:
    path = _safe_audio(config.PREVIEWS_DIR, filename)
    return FileResponse(path, media_type="audio/wav", filename=filename)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@router.get("/history")
def list_history(limit: int = 100) -> dict:
    return {"items": HISTORY.list(limit=limit)}


@router.delete("/history/{entry_id}")
def delete_history(entry_id: str) -> dict:
    if not HISTORY.delete(entry_id):
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"deleted": True}


@router.delete("/history")
def clear_history() -> dict:
    removed = HISTORY.clear()
    return {"removed": removed}
