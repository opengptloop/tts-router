"""Health, system status, logs and settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from .. import config, hardware
from ..logbus import BUS
from ..model_manager import get_manager
from ..schemas import SettingsUpdate
from ..storage import SETTINGS

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
    }


@router.get("/system/status")
def system_status() -> dict:
    status = hardware.system_status()
    manager = get_manager()
    status["engines"] = manager.status()
    return status


@router.get("/logs")
def logs(
    after: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    return {
        "items": BUS.tail(after_seq=after, limit=limit),
        "last_seq": BUS.last_seq,
    }


@router.delete("/logs")
def clear_logs() -> dict:
    BUS.clear()
    BUS.append("INFO", "tts.api", "Log buffer cleared")
    return {"ok": True}


@router.get("/settings")
def get_settings() -> dict:
    return SETTINGS.get()


@router.put("/settings")
def update_settings(payload: SettingsUpdate) -> dict:
    return SETTINGS.update(payload.settings)
