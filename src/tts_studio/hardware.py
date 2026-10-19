"""System hardware / resource reporting for the status panel."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import psutil

from . import config

_cache: dict[str, Any] = {"ts": 0.0, "value": None}
_dir_size_cache: dict[str, tuple[float, int]] = {}


def _dir_size(path: Path) -> int:
    now = time.time()
    cached = _dir_size_cache.get(str(path))
    if cached and now - cached[0] < 60:
        return cached[1]
    total = 0
    if path.exists():
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
    _dir_size_cache[str(path)] = (now, total)
    return total


def gpu_info() -> list[dict[str, Any]]:
    if importlib.util.find_spec("torch") is None:
        return []
    try:
        import torch  # type: ignore

        if not torch.cuda.is_available():
            return []
        gpus = []
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            free, total = torch.cuda.mem_get_info(index)
            gpus.append(
                {
                    "index": index,
                    "name": props.name,
                    "vram_total": total,
                    "vram_used": total - free,
                    "cuda": torch.version.cuda,
                }
            )
        return gpus
    except Exception:  # pragma: no cover - defensive
        return []


def torch_version() -> str | None:
    if importlib.util.find_spec("torch") is None:
        return None
    try:
        import torch  # type: ignore

        return torch.__version__
    except Exception:  # pragma: no cover
        return None


def cache_usage() -> dict[str, int]:
    return {
        "hf_cache": _dir_size(config.HF_CACHE_DIR),
        "piper_voices": _dir_size(config.PIPER_VOICES_DIR),
        "audio_outputs": _dir_size(config.OUTPUTS_DIR),
        "custom_voices": _dir_size(config.CUSTOM_VOICES_DIR),
    }


def system_status() -> dict[str, Any]:
    now = time.time()
    if _cache["value"] is not None and now - _cache["ts"] < 2.0:
        return _cache["value"]

    cpu_freq = psutil.cpu_freq()
    memory = psutil.virtual_memory()
    disk = shutil.disk_usage(str(config.DATA_DIR))

    status = {
        "app": {
            "name": config.APP_NAME,
            "version": config.APP_VERSION,
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
        },
        "platform": platform.platform(),
        "cpu": {
            "count": psutil.cpu_count(logical=True),
            "percent": psutil.cpu_percent(interval=None),
            "freq_mhz": round(cpu_freq.current) if cpu_freq else None,
        },
        "ram": {
            "total": memory.total,
            "used": memory.total - memory.available,
            "percent": memory.percent,
        },
        "disk": {
            "data_dir": str(config.DATA_DIR),
            "total": disk.total,
            "free": disk.free,
        },
        "gpus": gpu_info(),
        "torch": torch_version(),
        "cache_bytes": cache_usage(),
        "pid": os.getpid(),
    }
    _cache["ts"] = now
    _cache["value"] = status
    return status
