"""Kokoro-82M engine adapter.

Uses the official ``kokoro`` package (https://github.com/hexgrad/kokoro).
One ``KModel`` is loaded once and shared between language-specific
``KPipeline`` instances (the pattern recommended by the upstream docs).
"""

from __future__ import annotations

import logging
from typing import Any

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
from .catalogs import KOKORO_LANGUAGES, KOKORO_VARIANTS, KOKORO_VOICES

logger = logging.getLogger("tts.engines.kokoro")

_KOKORO_BY_ID = {voice["id"]: voice for voice in KOKORO_VOICES}
_LOGURU_WIRED = False


class KokoroEngine(BaseEngine):
    id = "kokoro"
    name = "Kokoro TTS"
    description = (
        "Kokoro-82M: lightweight Apache-2.0 model with 54 voices across 9 "
        "languages. Very fast on CPU."
    )
    homepage = "https://github.com/hexgrad/kokoro"
    license = "Apache-2.0"
    import_names = ["kokoro", "misaki", "torch"]
    default_variant = "kokoro-82m"
    cloning = False  # voice tensors, not zero-shot cloning
    install_specs = {
        "base": ["kokoro>=0.9.4", "soundfile"],
        "extras": {
            "ja": {"label": "Japanese G2P (misaki[ja])", "packages": ["misaki[ja]"]},
            "zh": {"label": "Chinese G2P (misaki[zh])", "packages": ["misaki[zh]"]},
        },
    }
    custom_voice_types = [
        {
            "kind": "tensor",
            "label": "Voice tensor (.pt)",
            "accept": ".pt",
            "help": "A 510x1x256 voice embedding compatible with Kokoro-82M.",
            "fields": ["language"],
        }
    ]

    # ------------------------------------------------------------------
    def variants(self) -> list[dict[str, Any]]:
        return [
            {
                **variant,
                "load_options": [
                    option(
                        "device",
                        "Device",
                        "select",
                        "cpu",
                        ["cpu", "cuda", "mps", "auto"],
                        help_="CPU by default. 'auto' picks CUDA/MPS when available.",
                    ),
                ],
                "gen_options": [
                    option("speed", "Speed", "float", 1.0, minimum=0.5, maximum=2.0,
                           step=0.05, help_="<1 slower, >1 faster"),
                    option("seed", "Seed", "int", None, advanced=True,
                           help_="Optional torch RNG seed for reproducible audio"),
                ],
            }
            for variant in KOKORO_VARIANTS
        ]

    def voices(
        self, variant_id: str | None, custom_voices: list[Any] | None = None
    ) -> list[Voice]:
        voices = [
            Voice(
                id=entry["id"],
                name=f"{entry['id']}  ·  {entry['description']}",
                language=entry["language"],
                lang_code=entry["lang_code"],
                gender=entry["gender"],
                description=entry["description"],
                grade=entry["grade"],
                tags=entry["tags"],
                variants=["kokoro-82m"],
                extra={"flag": entry["flag"]},
            )
            for entry in KOKORO_VOICES
        ]
        for custom in custom_voices or []:
            voices.append(
                Voice(
                    id=f"custom:{custom['id']}",
                    name=custom["name"],
                    language=KOKORO_LANGUAGES.get(
                        custom.get("language") or "a", {}
                    ).get("name", "American English"),
                    lang_code=custom.get("language") or "a",
                    gender=None,
                    description="Custom voice tensor",
                    custom=True,
                    path=custom.get("path"),
                    variants=["kokoro-82m"],
                    extra={"flag": "🧬"},
                )
            )
        return voices

    # ------------------------------------------------------------------
    def _wire_loguru(self) -> None:
        """Forward Kokoro's loguru output into the studio log bus."""
        global _LOGURU_WIRED
        if _LOGURU_WIRED:
            return
        try:
            from loguru import logger as loguru_logger

            from ..logbus import BUS

            loguru_logger.enable("kokoro")
            loguru_logger.add(
                lambda message: BUS.append(
                    message.record["level"].name,
                    "kokoro",
                    str(message).rstrip("\n"),
                ),
                level="INFO",
            )
            _LOGURU_WIRED = True
        except Exception:  # pragma: no cover - best effort
            pass

    def load(self, variant_id: str, options: dict[str, Any]) -> LoadedHandle:
        from kokoro import KModel

        self._wire_loguru()

        device = (options.get("device") or "cpu").lower()
        torch_device: str | None = device
        if device == "auto":
            torch_device = None

        if torch_device == "cuda":
            import torch

            if not torch.cuda.is_available():
                raise EngineError(
                    "CUDA was requested but torch.cuda.is_available() is False. "
                    "Install a CUDA-enabled torch build or pick CPU.",
                    code="device_unavailable",
                )
        if torch_device == "mps":
            import os

            import torch

            if not torch.backends.mps.is_available():
                raise EngineError(
                    "MPS was requested but is not available on this machine.",
                    code="device_unavailable",
                )
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

        repo_id = config.KOKORO_REPO
        logger.info(
            "Loading Kokoro-82M (repo=%s, device=%s). Weights download on first use.",
            repo_id,
            device,
        )
        model = KModel(repo_id=repo_id)
        if torch_device:
            model = model.to(torch_device)
        else:
            device = str(model.device)
        model = model.eval()

        handle = {
            "model": model,
            "pipelines": {},
            "device": device,
            "repo_id": repo_id,
        }
        return LoadedHandle(
            engine_id=self.id,
            variant_id=variant_id or self.default_variant,
            options={"device": device},
            handle=handle,
            device=device,
            sample_rate=config.KOKORO_SAMPLE_RATE,
            meta={"repo_id": repo_id},
        )

    # ------------------------------------------------------------------
    def _pipeline_for(self, loaded: LoadedHandle, lang_code: str):
        from kokoro import KPipeline

        handle = loaded.handle
        pipelines = handle["pipelines"]
        if lang_code not in pipelines:
            logger.info("Creating Kokoro pipeline for lang_code='%s'", lang_code)
            pipelines[lang_code] = KPipeline(
                lang_code=lang_code,
                model=handle["model"],
                repo_id=handle["repo_id"],
            )
        return pipelines[lang_code]

    def _lang_code_for(self, voice: VoiceRef) -> str:
        if voice.language:
            return voice.language
        if voice.kind == "builtin":
            entry = _KOKORO_BY_ID.get(voice.value)
            if entry:
                return entry["lang_code"]
            prefix = (voice.value or "a")[0].lower()
            if prefix in KOKORO_LANGUAGES:
                return prefix
        return "a"

    def generate(
        self,
        loaded: LoadedHandle,
        text: str,
        voice: VoiceRef,
        options: dict[str, Any],
        progress,
        cancelled,
    ) -> GenerationResult:
        import torch

        speed = float(options.get("speed") or 1.0)
        seed = options.get("seed")
        if seed not in (None, ""):
            torch.manual_seed(int(seed))

        lang_code = self._lang_code_for(voice)
        pipeline = self._pipeline_for(loaded, lang_code)
        voice_value = voice.value  # builtin name or local .pt path

        if lang_code in ("j", "z"):
            try:
                logger.info("Synthesizing with Kokoro lang_code='%s'", lang_code)
            except Exception:
                pass

        total_chars = max(1, len(text.strip()))
        parts: list[np.ndarray] = []
        done_chars = 0

        try:
            results = pipeline(text.strip(), voice=voice_value, speed=speed)
        except ImportError as exc:
            raise EngineError(
                f"Missing G2P dependency for language '{lang_code}': {exc}. "
                "Install the optional misaki extras for this language.",
                code="missing_dependency",
            ) from exc

        for result in results:
            if cancelled():
                raise CancelledError("Cancelled during Kokoro generation")
            if result.audio is None:
                continue
            parts.append(result.audio.detach().cpu().numpy().astype(np.float32))
            done_chars += len(result.graphemes or "")
            progress(min(0.99, done_chars / total_chars), None)

        if not parts:
            raise EngineError("Kokoro produced no audio for this input.")

        audio = (
            np.concatenate(parts)
            if len(parts) > 1
            else parts[0]
        )
        return GenerationResult(
            audio=audio,
            sample_rate=config.KOKORO_SAMPLE_RATE,
            meta={"lang_code": lang_code, "speed": speed},
        )
