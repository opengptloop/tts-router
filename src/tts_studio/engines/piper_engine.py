"""Piper TTS engine adapter (OHF-Voice/piper1-gpl).

Piper ships a huge voice catalogue (177 voices across 58 languages). Voices
are downloaded on demand from ``rhasspy/piper-voices`` into the local data
directory and must be present before they can be used.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from .. import config
from ..jobs import CancelledError
from .base import (
    BaseEngine,
    EngineError,
    GenerationResult,
    LoadedHandle,
    Voice,
    VoiceRef,
    option,
)

logger = logging.getLogger("tts.engines.piper")

MAX_LOADED_VOICES = 4


def _voice_paths(key: str) -> tuple[Path, Path]:
    return (
        config.PIPER_VOICES_DIR / f"{key}.onnx",
        config.PIPER_VOICES_DIR / f"{key}.onnx.json",
    )


class PiperCatalog:
    """Fetches and caches the official rhasspy/piper-voices catalogue."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._voices: dict[str, dict[str, Any]] | None = None
        self._fetched_at: float = 0.0

    # -- persistence -------------------------------------------------------
    def _load_disk(self) -> bool:
        path = config.PIPER_CATALOG_FILE
        if not path.is_file():
            return False
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self._voices = payload.get("voices") or {}
            self._fetched_at = float(payload.get("fetched_at") or 0)
            return bool(self._voices)
        except (json.JSONDecodeError, OSError, ValueError):
            return False

    def _save_disk(self) -> None:
        path = config.PIPER_CATALOG_FILE
        temp = path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(
                {"fetched_at": self._fetched_at, "voices": self._voices},
                handle,
            )
        temp.replace(path)

    # -- public ------------------------------------------------------------
    def get(self, force: bool = False) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._voices and not force:
                age = time.time() - self._fetched_at
                if age < config.PIPER_CATALOG_TTL:
                    return self._voices
            if self._voices is None:
                self._load_disk()
                if (
                    self._voices
                    and not force
                    and time.time() - self._fetched_at < config.PIPER_CATALOG_TTL
                ):
                    return self._voices

            try:
                logger.info("Fetching Piper voice catalogue (voices.json)")
                with httpx.Client(timeout=60, follow_redirects=True) as client:
                    response = client.get(config.PIPER_CATALOG_URL)
                    response.raise_for_status()
                    raw = response.json()
                self._voices = {
                    key: self._normalize(key, entry) for key, entry in raw.items()
                }
                self._fetched_at = time.time()
                self._save_disk()
                logger.info("Piper catalogue loaded: %d voices", len(self._voices))
            except Exception as exc:
                if self._voices:
                    logger.warning(
                        "Could not refresh Piper catalogue (%s); using cached copy",
                        exc,
                    )
                elif self._load_disk():
                    logger.warning(
                        "Could not fetch Piper catalogue (%s); using cached copy", exc
                    )
                else:
                    raise EngineError(
                        "Could not fetch the Piper voice catalogue from "
                        "huggingface.co. Check your internet connection.",
                        code="catalog_unavailable",
                    ) from exc
            return self._voices

    @staticmethod
    def _normalize(key: str, entry: dict[str, Any]) -> dict[str, Any]:
        files = entry.get("files") or {}
        onnx_path = next((p for p in files if p.endswith(".onnx")), None)
        config_path = next(
            (p for p in files if p.endswith(".onnx.json")), None
        )
        size = sum(
            files[p].get("size_bytes", 0)
            for p in (onnx_path, config_path)
            if p
        )
        language = entry.get("language") or {}
        return {
            "key": key,
            "name": entry.get("name"),
            "quality": entry.get("quality"),
            "num_speakers": entry.get("num_speakers", 1),
            "speaker_id_map": entry.get("speaker_id_map") or {},
            "language": {
                "code": language.get("code"),
                "family": language.get("family"),
                "region": language.get("region"),
                "name_native": language.get("name_native"),
                "name_english": language.get("name_english"),
                "country_english": language.get("country_english"),
            },
            "onnx_path": onnx_path,
            "config_path": config_path,
            "size_bytes": size,
            "aliases": entry.get("aliases") or [],
        }

    # -- local status ------------------------------------------------------
    def local_status(self, key: str) -> str:
        onnx, config_path = _voice_paths(key)
        if onnx.is_file() and config_path.is_file():
            return "downloaded"
        if onnx.is_file() or config_path.is_file():
            return "partial"
        return "missing"


CATALOG = PiperCatalog()


class PiperEngine(BaseEngine):
    id = "piper"
    name = "Piper TTS"
    description = (
        "Piper (OHF-Voice): fast local neural TTS with a catalog of 177 voices "
        "across 58 languages. Voices download on demand."
    )
    homepage = "https://github.com/OHF-Voice/piper1-gpl"
    license = "MIT"
    import_names = ["piper", "onnxruntime"]
    default_variant = "piper"
    cloning = False
    install_specs = {"base": ["piper-tts"]}
    custom_voice_types = [
        {
            "kind": "onnx",
            "label": "Piper voice (.onnx + .onnx.json)",
            "accept": ".onnx,.onnx.json",
            "help": "Upload both files together for a custom Piper voice.",
            "fields": [],
            "multiple": True,
        }
    ]

    # ------------------------------------------------------------------
    def variants(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "piper",
                "label": "Piper voices (ONNX)",
                "description": (
                    "Voices are independent ONNX models. Download them from the "
                    "voice catalog; every downloaded voice shares this runtime."
                ),
                "repo": "rhasspy/piper-voices",
                "size_hint": "20 MB - 120 MB per voice",
                "download_required": True,
                "cloning": False,
                "load_options": [
                    option(
                        "use_cuda",
                        "Use CUDA",
                        "bool",
                        False,
                        help_="Requires onnxruntime-gpu.",
                    ),
                ],
                "gen_options": [
                    option(
                        "speed",
                        "Speed",
                        "float",
                        1.0,
                        minimum=0.5,
                        maximum=2.0,
                        step=0.05,
                        help_="Maps to 1/length_scale.",
                    ),
                    option(
                        "noise_scale",
                        "Noise scale",
                        "float",
                        None,
                        minimum=0.0,
                        maximum=2.0,
                        step=0.05,
                        advanced=True,
                        help_="Variation between samples.",
                    ),
                    option(
                        "noise_w_scale",
                        "Noise W scale",
                        "float",
                        None,
                        minimum=0.0,
                        maximum=2.0,
                        step=0.05,
                        advanced=True,
                        help_="Speaking rhythm variation.",
                    ),
                    option(
                        "volume",
                        "Volume",
                        "float",
                        1.0,
                        minimum=0.0,
                        maximum=2.0,
                        step=0.05,
                        advanced=True,
                    ),
                ],
            }
        ]

    # ------------------------------------------------------------------
    def voices(
        self, variant_id: str | None, custom_voices: list[Any] | None = None
    ) -> list[Voice]:
        entries = CATALOG.get()
        voices: list[Voice] = []
        for key, entry in entries.items():
            language = entry["language"]
            speakers = [
                {"id": int(sid), "name": sname}
                for sname, sid in (entry["speaker_id_map"] or {}).items()
            ]
            voices.append(
                Voice(
                    id=key,
                    name=key,
                    language=(
                        language.get("name_english")
                        or language.get("name_native")
                        or "Unknown"
                    ),
                    lang_code=language.get("code"),
                    gender=None,
                    description=(
                        f"{language.get('country_english') or ''} · "
                        f"quality: {entry['quality']}"
                    ).strip(" ·"),
                    variants=["piper"],
                    speaker_count=entry["num_speakers"],
                    speakers=speakers,
                    size_bytes=entry["size_bytes"],
                    downloaded=CATALOG.local_status(key) == "downloaded",
                    extra={
                        "quality": entry["quality"],
                        "language_code": language.get("code"),
                        "language_name": language.get("name_english"),
                        "country": language.get("country_english"),
                        "flag": _flag_for(language.get("code") or ""),
                        "aliases": entry.get("aliases") or [],
                    },
                )
            )
        for custom in custom_voices or []:
            voices.append(
                Voice(
                    id=f"custom:{custom['id']}",
                    name=custom["name"],
                    language="Custom",
                    lang_code="xx",
                    description="Custom Piper voice (.onnx)",
                    custom=True,
                    downloaded=True,
                    path=custom.get("path"),
                    variants=["piper"],
                    extra={"quality": "custom", "flag": "🧬"},
                )
            )
        return voices

    # ------------------------------------------------------------------
    def load(self, variant_id: str, options: dict[str, Any]) -> LoadedHandle:
        # The runtime itself is trivial; individual voices are loaded lazily.
        handle = {
            "sessions": OrderedDict(),
            "use_cuda": bool(options.get("use_cuda", False)),
            "lock": threading.RLock(),
        }
        return LoadedHandle(
            engine_id=self.id,
            variant_id="piper",
            options={"use_cuda": handle["use_cuda"]},
            handle=handle,
            device="cuda" if handle["use_cuda"] else "cpu",
            sample_rate=22050,
        )

    def unload(self, loaded: LoadedHandle) -> None:
        handle = loaded.handle
        try:
            handle["sessions"].clear()
        except Exception:  # pragma: no cover
            pass
        super().unload(loaded)

    # ------------------------------------------------------------------
    def _session_for(self, loaded: LoadedHandle, voice: VoiceRef) -> Any:
        from piper import PiperVoice

        handle = loaded.handle
        use_cuda = handle["use_cuda"]

        if voice.kind == "file":
            onnx_path = Path(voice.value)
            config_path = Path(str(voice.value) + ".json")
            if not config_path.is_file():
                # Custom piper voices store the config next to the model.
                candidates = sorted(onnx_path.parent.glob("*.onnx.json"))
                if not candidates:
                    raise EngineError(
                        "Piper custom voice is missing its .onnx.json config.",
                        code="voice_broken",
                    )
                config_path = candidates[0]
            cache_key = f"file:{onnx_path}"
        else:
            onnx_path, config_path = _voice_paths(voice.value)
            cache_key = f"voice:{voice.value}"
            if not onnx_path.is_file() or not config_path.is_file():
                raise EngineError(
                    f"Piper voice '{voice.value}' is not downloaded yet. "
                    "Download it from the Models page first.",
                    code="voice_not_downloaded",
                )

        with handle["lock"]:
            sessions = handle["sessions"]
            if cache_key in sessions:
                sessions.move_to_end(cache_key)
                return sessions[cache_key]
            logger.info(
                "Loading Piper voice %s (device=%s)",
                cache_key,
                "cuda" if use_cuda else "cpu",
            )
            session = PiperVoice.load(
                str(onnx_path), config_path=str(config_path), use_cuda=use_cuda
            )
            sessions[cache_key] = session
            while len(sessions) > MAX_LOADED_VOICES:
                sessions.popitem(last=False)
            return session

    # ------------------------------------------------------------------
    def download_voice(
        self,
        key: str,
        progress,
        cancelled,
    ) -> dict[str, Any]:
        """Download .onnx + .onnx.json for a catalogue voice."""
        entries = CATALOG.get()
        entry = entries.get(key)
        if entry is None:
            raise EngineError(f"Unknown Piper voice '{key}'", code="unknown_voice")
        onnx_target, config_target = _voice_paths(key)

        if CATALOG.local_status(key) == "downloaded":
            return {"key": key, "already_downloaded": True}

        targets = [
            (entry["onnx_path"], onnx_target),
            (entry["config_path"], config_target),
        ]
        targets = [(rel, path) for rel, path in targets if rel]
        if not targets:
            raise EngineError(
                f"Catalogue entry for '{key}' has no downloadable files.",
                code="catalogue_error",
            )

        config.PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        total_bytes = 0
        with httpx.Client(timeout=httpx.Timeout(30, read=300), follow_redirects=True) as client:
            for rel_path, target in targets:
                url = config.PIPER_VOICE_BASE_URL + rel_path
                logger.info("Downloading Piper voice file %s", url)
                temp = target.with_suffix(target.suffix + ".part")
                hasher = hashlib.md5()
                downloaded = 0
                try:
                    with client.stream("GET", url) as response:
                        response.raise_for_status()
                        expected = int(response.headers.get("content-length", 0))
                        with open(temp, "wb") as handle:
                            for chunk in response.iter_bytes(1024 * 256):
                                if cancelled():
                                    raise CancelledError("Download cancelled")
                                handle.write(chunk)
                                hasher.update(chunk)
                                downloaded += len(chunk)
                                if expected:
                                    progress(
                                        0.05 + 0.9 * (downloaded / expected) * 0.5
                                        + (0.45 if total_bytes else 0),
                                        f"{target.name}: {downloaded // 1024} KiB",
                                    )
                    temp.replace(target)
                except Exception:
                    temp.unlink(missing_ok=True)
                    raise
                total_bytes += downloaded

        if CATALOG.local_status(key) != "downloaded":
            raise EngineError(
                f"Download of '{key}' did not complete.", code="download_incomplete"
            )
        return {"key": key, "size_bytes": total_bytes}

    def delete_voice(self, key: str) -> bool:
        onnx_target, config_target = _voice_paths(key)
        removed = False
        for target in (onnx_target, config_target):
            if target.is_file():
                target.unlink()
                removed = True
        if removed:
            logger.info("Deleted Piper voice files for %s", key)
        return removed

    # ------------------------------------------------------------------
    def generate(
        self,
        loaded: LoadedHandle,
        text: str,
        voice: VoiceRef,
        options: dict[str, Any],
        progress,
        cancelled,
    ) -> GenerationResult:
        from piper import SynthesisConfig

        session = self._session_for(loaded, voice)
        speed = float(options.get("speed") or 1.0)
        if speed <= 0:
            speed = 1.0

        syn_config = SynthesisConfig(
            speaker_id=(
                int(options["speaker_id"])
                if options.get("speaker_id") not in (None, "")
                else None
            ),
            length_scale=1.0 / speed,
            noise_scale=(
                float(options["noise_scale"])
                if options.get("noise_scale") not in (None, "")
                else None
            ),
            noise_w_scale=(
                float(options["noise_w_scale"])
                if options.get("noise_w_scale") not in (None, "")
                else None
            ),
            volume=float(options.get("volume") or 1.0),
        )

        progress(0.02, "Phonemizing")
        parts: list[np.ndarray] = []
        phoneme_total = 0
        estimated_total = max(1.0, len(text) * 1.2)
        for chunk in session.synthesize(text, syn_config=syn_config):
            if cancelled():
                raise CancelledError("Cancelled during Piper generation")
            parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32).reshape(-1))
            phoneme_total += len(chunk.phonemes or [])
            progress(min(0.99, phoneme_total / estimated_total), None)

        if not parts:
            raise EngineError("Piper produced no audio for this input.")

        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        return GenerationResult(
            audio=audio,
            sample_rate=int(session.config.sample_rate),
            meta={"voice": voice.value},
        )


def _flag_for(code: str) -> str:
    """Map a locale like en_US / de_DE to a flag emoji."""
    if not code or "_" not in code:
        return "🌐"
    region = code.split("_", 1)[1].upper()
    if len(region) != 2 or not region.isalpha():
        return "🌐"
    return chr(0x1F1E6 + ord(region[0]) - ord("A")) + chr(
        0x1F1E6 + ord(region[1]) - ord("A")
    )
