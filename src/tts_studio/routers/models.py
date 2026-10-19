"""Model / engine management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..jobs import JOBS
from ..model_manager import get_manager
from ..schemas import InstallRequest, LoadRequest

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
def list_models() -> dict:
    manager = get_manager()
    engines = []
    for engine_id, engine in manager.engines.items():
        info = engine.describe()
        info["install_targets"] = manager.installable_specs(engine_id)
        info["variants"] = manager.variants_with_status(engine_id)
        status = manager.status()[engine_id]
        info.update(
            {
                "loaded": status["loaded"],
                "loaded_variant": status["loaded_variant"],
                "loaded_at": status["loaded_at"],
                "device": status["device"],
                "load_options": status["load_options"],
                "loaded_voices": status.get("loaded_voices"),
            }
        )
        engines.append(info)
    return {"engines": engines}


@router.post("/models/{engine_id}/install")
def install_engine(engine_id: str, payload: InstallRequest) -> dict:
    manager = get_manager()
    engine = manager.engine(engine_id)
    job = JOBS.submit(
        "install",
        f"Install {engine.name} ({payload.spec})",
        lambda ctx: manager.install_engine(
            engine_id,
            payload.spec,
            log=lambda message: ctx.log(message),
            cancelled=ctx.is_cancelled,
        ),
        pool="io",
    )
    return {"job_id": job.id}


@router.post("/models/{engine_id}/load")
def load_model(engine_id: str, payload: LoadRequest) -> dict:
    manager = get_manager()
    engine = manager.engine(engine_id)
    variant = payload.variant or engine.default_variant
    options = {**manager.default_load_options(engine, variant), **payload.options}
    job = JOBS.submit(
        "load",
        f"Load {engine.name} · {variant}",
        lambda ctx: _load_job(manager, engine_id, variant, options, ctx),
        pool="compute",
    )
    return {"job_id": job.id}


def _load_job(manager, engine_id: str, variant: str, options: dict, ctx) -> dict:
    handle = manager.load_model(
        engine_id,
        variant,
        options,
        progress=lambda fraction, message: ctx.progress(fraction, message),
    )
    return {
        "engine": engine_id,
        "variant": handle.variant_id,
        "device": handle.device,
        "sample_rate": handle.sample_rate,
    }


@router.post("/models/{engine_id}/unload")
def unload_model(engine_id: str) -> dict:
    manager = get_manager()
    manager.engine(engine_id)
    unloaded = manager.unload_model(engine_id)
    return {"unloaded": unloaded}


@router.get("/jobs")
def list_jobs(limit: int = 50) -> dict:
    return {"jobs": JOBS.list(limit=limit)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    snapshot = JOBS.snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    if not JOBS.cancel(job_id):
        raise HTTPException(status_code=409, detail="Job cannot be cancelled")
    return {"ok": True}
