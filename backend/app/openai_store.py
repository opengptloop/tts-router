"""Persistence and rate limiting for the OpenAI-compatible API layer.

Two JSON files live inside the data directory:

- ``api_keys.json``  — API keys clients use as ``Authorization: Bearer <key>``
- ``api_config.json`` — the single active TTS configuration (engine, voice,
  speed, default output format, auth mode), configured exclusively from the
  in-app "API" page.

Keys are stored in plain text on purpose: this is a local-first, single-user
application and the owner can always re-copy a key from the API page. The
files are only readable by whoever can already read the data directory.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Any

from . import config
from .storage import _read_json, _write_json

logger = logging.getLogger("tts.openai.store")

KEY_PREFIX = "sk-tts-"

RESPONSE_FORMATS = ["mp3", "opus", "aac", "flac", "wav", "pcm"]

# Formats that require an ffmpeg binary on the host.
FFMPEG_FORMATS = {"mp3", "opus", "aac"}

DEFAULT_CONFIG: dict[str, Any] = {
    # The ONE TTS engine that serves /v1/audio/speech. Clients cannot choose.
    "engine": None,
    # Engine variant / flavour (e.g. "piper", "kokoro-82m"). None = default.
    "variant": None,
    # The ONE voice used for every request. Clients cannot choose.
    "voice": None,
    "speed": 1.0,
    "response_format": "mp3",
    # When False the endpoint is open: no Authorization header required.
    "require_api_key": False,
    "max_input_chars": 4096,
}


def new_key() -> str:
    return KEY_PREFIX + secrets.token_hex(24)


class RateLimiter:
    """In-memory sliding window (per key), 60 second window."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key_id: str, limit_per_min: int | None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        if not limit_per_min or limit_per_min <= 0:
            return True, 0
        now = time.time()
        window_start = now - 60.0
        with self._lock:
            bucket = self._events[key_id]
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= limit_per_min:
                retry_after = int(max(1.0, 60.0 - (now - bucket[0]))) + 1
                return False, retry_after
            bucket.append(now)
            return True, 0

    def reset(self, key_id: str) -> None:
        with self._lock:
            self._events.pop(key_id, None)


RATE_LIMITER = RateLimiter()


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


class ApiKeyStore:
    def __init__(self, path) -> None:
        self.path = path

    def _load(self) -> list[dict[str, Any]]:
        data = _read_json(self.path, [])
        return data if isinstance(data, list) else []

    def _save(self, keys: list[dict[str, Any]]) -> None:
        _write_json(self.path, keys)

    def list(self) -> list[dict[str, Any]]:
        keys = self._load()
        keys.sort(key=lambda k: k.get("created_at", 0), reverse=True)
        return keys

    def active(self) -> list[dict[str, Any]]:
        return [key for key in self._load() if not key.get("revoked")]

    def get(self, key_id: str) -> dict[str, Any] | None:
        for key in self._load():
            if key.get("id") == key_id:
                return key
        return None

    def verify(self, token: str) -> dict[str, Any] | None:
        """Return the matching active key record, or None."""
        if not token:
            return None
        for key in self.active():
            if secrets.compare_digest(str(key.get("key", "")), token):
                return key
        return None

    def create(self, name: str, rate_limit_per_min: int | None = None) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex[:12],
            "name": (name or "Untitled key").strip()[:80],
            "key": new_key(),
            "created_at": time.time(),
            "last_used_at": None,
            "request_count": 0,
            "rate_limit_per_min": max(0, int(rate_limit_per_min or 0)) or None,
            "revoked": False,
        }
        keys = self._load()
        keys.append(record)
        self._save(keys)
        logger.info("Created API key '%s' (%s)", record["name"], record["id"])
        return record

    def record_usage(self, key_id: str) -> None:
        keys = self._load()
        for key in keys:
            if key.get("id") == key_id:
                key["request_count"] = int(key.get("request_count") or 0) + 1
                key["last_used_at"] = time.time()
                break
        else:
            return
        self._save(keys)

    def update(self, key_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        keys = self._load()
        updated = None
        for key in keys:
            if key.get("id") == key_id:
                if "name" in patch:
                    key["name"] = (str(patch["name"]) or "Untitled key").strip()[:80]
                if "rate_limit_per_min" in patch:
                    value = patch["rate_limit_per_min"]
                    key["rate_limit_per_min"] = (
                        max(0, int(value)) if value not in (None, "") else None
                    )
                if "revoked" in patch:
                    key["revoked"] = bool(patch["revoked"])
                updated = key
                break
        if updated is not None:
            self._save(keys)
            RATE_LIMITER.reset(key_id)
        return updated

    def delete(self, key_id: str) -> bool:
        keys = self._load()
        kept = [key for key in keys if key.get("id") != key_id]
        if len(kept) == len(keys):
            return False
        self._save(kept)
        RATE_LIMITER.reset(key_id)
        return True

    def revoke_all(self) -> int:
        keys = self._load()
        count = 0
        for key in keys:
            if not key.get("revoked"):
                key["revoked"] = True
                count += 1
        if count:
            self._save(keys)
        return count


API_KEYS = ApiKeyStore(config.API_KEYS_FILE)


# ---------------------------------------------------------------------------
# Active TTS configuration (single engine + voice, auth mode, defaults)
# ---------------------------------------------------------------------------


def _migrate_legacy(data: dict[str, Any]) -> dict[str, Any] | None:
    """Convert the old ``mappings`` schema into the new active-config shape.

    The previous design let admins expose many public model names, each mapped
    to an engine/voice pair. The simplified API exposes exactly one engine and
    one voice, so the first enabled mapping becomes the active configuration.
    """
    mappings = data.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        return None
    mapping = next(
        (m for m in mappings if isinstance(m, dict) and m.get("enabled") and m.get("engine")),
        None,
    )
    if mapping is None:
        return None
    defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    migrated = {**DEFAULT_CONFIG}
    migrated["engine"] = str(mapping.get("engine") or "").strip() or None
    migrated["variant"] = str(mapping.get("variant") or "").strip() or None
    migrated["voice"] = (
        str(mapping.get("voice") or "").strip() or str(defaults.get("voice") or "").strip() or None
    )
    for key in ("speed", "response_format", "max_input_chars"):
        if defaults.get(key) is not None:
            migrated[key] = defaults[key]
    logger.info(
        "Migrated legacy API config: mapping '%s' -> engine '%s' voice '%s'",
        mapping.get("model"),
        migrated["engine"],
        migrated["voice"],
    )
    return migrated


class ActiveConfigStore:
    """The single TTS configuration served by ``/v1/audio/speech``."""

    def __init__(self, path) -> None:
        self.path = path

    def get(self) -> dict[str, Any]:
        data = _read_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        if "mappings" in data:
            migrated = _migrate_legacy(data)
            if migrated is not None:
                data = migrated
                _write_json(self.path, migrated)
            else:
                data = {}
        return {**DEFAULT_CONFIG, **data}

    def save(
        self,
        engine: str,
        voice: str,
        *,
        variant: str | None = None,
        speed: float = 1.0,
        response_format: str = "mp3",
        require_api_key: bool = False,
        max_input_chars: int = 4096,
    ) -> dict[str, Any]:
        if not str(engine or "").strip():
            raise ValueError("Pick a TTS model before saving the configuration.")
        if not str(voice or "").strip():
            raise ValueError("Pick a voice before saving the configuration.")
        fmt = str(response_format or "").strip().lower()
        if fmt not in RESPONSE_FORMATS:
            raise ValueError(f"Unsupported output format '{response_format}'.")
        clean = {
            "engine": str(engine).strip(),
            "variant": (str(variant).strip() if variant else None),
            "voice": str(voice).strip(),
            "speed": min(4.0, max(0.25, float(speed or 1.0))),
            "response_format": fmt,
            "require_api_key": bool(require_api_key),
            "max_input_chars": min(100000, max(1, int(max_input_chars or 4096))),
        }
        _write_json(self.path, clean)
        return clean

    def update_auth_mode(self, require_api_key: bool) -> dict[str, Any]:
        """Toggle only the auth mode, preserving everything else."""
        merged = self.get()
        merged["require_api_key"] = bool(require_api_key)
        _write_json(self.path, merged)
        return merged


ACTIVE_CONFIG = ActiveConfigStore(config.API_CONFIG_FILE)
