"""Local persistence: generation history, custom voices, settings."""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO

from . import config

logger = logging.getLogger("tts.storage")

_lock = threading.RLock()

_LANG_TAG_RE = re.compile(r"^[a-z]$")

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm"}


def _read_json(path: Path, default: Any) -> Any:
    with _lock:
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read %s, using default", path)
            return default


def _write_json(path: Path, data: Any) -> None:
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        temp.replace(path)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@dataclass
class HistoryEntry:
    id: str
    created_at: float
    engine: str
    model: str
    model_label: str
    voice: str
    voice_label: str
    text: str
    chars: int
    duration_s: float
    sample_rate: int
    wall_time_s: float
    file: str
    options: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at_iso"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.created_at)
        )
        data["audio_url"] = f"/api/audio/{self.file}"
        return data


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        entries = _read_json(self.path, [])
        entries = entries[:limit]
        return [self._with_urls(entry) for entry in entries]

    def _with_urls(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry = dict(entry)
        entry["audio_url"] = f"/api/audio/{entry['file']}"
        entry["created_at_iso"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(entry.get("created_at", 0))
        )
        return entry

    def add(self, entry: HistoryEntry) -> dict[str, Any]:
        entries = _read_json(self.path, [])
        entries.insert(0, asdict(entry))
        _write_json(self.path, entries[:500])
        return self._with_urls(asdict(entry))

    def delete(self, entry_id: str) -> bool:
        entries = _read_json(self.path, [])
        kept, removed = [], None
        for entry in entries:
            if entry.get("id") == entry_id:
                removed = entry
            else:
                kept.append(entry)
        if removed is None:
            return False
        _write_json(self.path, kept)
        audio = config.OUTPUTS_DIR / removed.get("file", "")
        try:
            if audio.is_file() and audio.parent == config.OUTPUTS_DIR:
                audio.unlink()
        except OSError:
            pass
        return True

    def clear(self) -> int:
        entries = _read_json(self.path, [])
        _write_json(self.path, [])
        for entry in entries:
            audio = config.OUTPUTS_DIR / entry.get("file", "")
            try:
                if audio.is_file() and audio.parent == config.OUTPUTS_DIR:
                    audio.unlink()
            except OSError:
                pass
        return len(entries)


HISTORY = HistoryStore(config.HISTORY_FILE)


# ---------------------------------------------------------------------------
# Custom voices
# ---------------------------------------------------------------------------


@dataclass
class CustomVoice:
    id: str
    engine: str
    name: str
    created_at: float
    files: list[str]
    kind: str  # tensor | onnx | reference
    language: str | None = None
    reference_text: str | None = None
    notes: str | None = None

    @property
    def directory(self) -> Path:
        return config.CUSTOM_VOICES_DIR / self.engine / self.id

    def primary_path(self) -> Path:
        return self.directory / self.files[0]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at_iso"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.created_at)
        )
        data["size_bytes"] = sum(
            (self.directory / name).stat().st_size
            for name in self.files
            if (self.directory / name).exists()
        )
        data["custom"] = True
        return data


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or uuid.uuid4().hex[:8]


class CustomVoiceStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _engine_dir(self, engine: str) -> Path:
        return self.root / engine

    def list(self, engine: str | None = None) -> list[CustomVoice]:
        engines = [engine] if engine else [
            path.name for path in self.root.iterdir() if path.is_dir()
        ] if self.root.exists() else []
        voices: list[CustomVoice] = []
        for engine_id in engines:
            directory = self._engine_dir(engine_id)
            if not directory.is_dir():
                continue
            for voice_dir in sorted(directory.iterdir()):
                meta_path = voice_dir / "meta.json"
                if not meta_path.is_file():
                    continue
                meta = _read_json(meta_path, None)
                if not meta:
                    continue
                try:
                    voices.append(CustomVoice(**meta))
                except TypeError:
                    logger.warning("Skipping malformed custom voice %s", voice_dir)
        return sorted(voices, key=lambda v: v.created_at, reverse=True)

    def get(self, engine: str, voice_id: str) -> CustomVoice | None:
        meta_path = self._engine_dir(engine) / voice_id / "meta.json"
        meta = _read_json(meta_path, None)
        if not meta:
            return None
        try:
            return CustomVoice(**meta)
        except TypeError:
            return None

    def add(
        self,
        engine: str,
        name: str,
        uploads: list[tuple[str, BinaryIO]],
        language: str | None = None,
        reference_text: str | None = None,
        notes: str | None = None,
    ) -> CustomVoice:
        """Validate and persist uploaded voice files.

        ``uploads`` is a list of ``(filename, file_object)`` pairs.
        """
        if not uploads:
            raise ValueError("No files were uploaded")
        if language and not _LANG_TAG_RE.match(language):
            raise ValueError("language must be a single letter language code")

        # Engine specific validation rules.
        kind = "reference"
        if engine == "kokoro":
            if len(uploads) != 1 or not uploads[0][0].lower().endswith(".pt"):
                raise ValueError("Kokoro custom voices require a single .pt tensor file")
            kind = "tensor"
        elif engine == "piper":
            names = [fn.lower() for fn, _ in uploads]
            onnx = [fn for fn in names if fn.endswith(".onnx")]
            configs = [fn for fn in names if fn.endswith(".onnx.json")]
            if len(uploads) != 2 or len(onnx) != 1 or len(configs) != 1:
                raise ValueError(
                    "Piper custom voices require exactly two files: "
                    "<voice>.onnx and <voice>.onnx.json"
                )
            kind = "onnx"
        elif engine == "kitten":
            if len(uploads) != 1:
                raise ValueError("Kitten voice cloning takes a single reference clip")
            if Path(uploads[0][0]).suffix.lower() not in AUDIO_EXTENSIONS:
                raise ValueError(
                    "Reference audio must be one of: "
                    + ", ".join(sorted(AUDIO_EXTENSIONS))
                )
        elif engine == "pocket":
            if len(uploads) != 1:
                raise ValueError("Pocket voices take a single clip or .safetensors file")
            suffix = Path(uploads[0][0]).suffix.lower()
            if suffix not in AUDIO_EXTENSIONS and suffix != ".safetensors":
                raise ValueError(
                    "Provide an audio clip or an exported .safetensors voice state"
                )
        else:
            raise ValueError(f"Unknown engine '{engine}'")

        voice_id = f"{slugify(name)}-{uuid.uuid4().hex[:6]}"
        directory = self._engine_dir(engine) / voice_id
        directory.mkdir(parents=True, exist_ok=True)
        saved_files: list[str] = []
        try:
            for filename, fileobj in uploads:
                safe_name = Path(filename).name
                target = directory / safe_name
                with open(target, "wb") as handle:
                    shutil.copyfileobj(fileobj, handle)
                saved_files.append(safe_name)
            voice = CustomVoice(
                id=voice_id,
                engine=engine,
                name=name.strip() or voice_id,
                created_at=time.time(),
                files=saved_files,
                kind=kind,
                language=language,
                reference_text=reference_text or None,
                notes=notes or None,
            )
            _write_json(directory / "meta.json", asdict(voice))
            logger.info(
                "Registered custom %s voice '%s' (%s)", engine, voice.name, voice.id
            )
            return voice
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def delete(self, engine: str, voice_id: str) -> bool:
        directory = self._engine_dir(engine) / voice_id
        if not (directory / "meta.json").is_file():
            return False
        shutil.rmtree(directory, ignore_errors=True)
        logger.info("Deleted custom %s voice %s", engine, voice_id)
        return True


CUSTOM_VOICES = CustomVoiceStore(config.CUSTOM_VOICES_DIR)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_load_on_generate": True,
    "keep_history": True,
    "default_engine": "kokoro",
}


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self) -> dict[str, Any]:
        data = _read_json(self.path, {})
        return {**DEFAULT_SETTINGS, **data}

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.get()
        data.update(patch or {})
        _write_json(self.path, data)
        return data


SETTINGS = SettingsStore(config.SETTINGS_FILE)
