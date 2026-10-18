"""Kyutai Pocket TTS engine adapter.

100M parameter CPU-first model with language specific configs and strong
voice cloning (any short sample, or exported ``.safetensors`` states).
Docs: https://github.com/kyutai-labs/pocket-tts
"""

from __future__ import annotations

import logging
import re
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
from .catalogs import POCKET_VARIANTS, POCKET_VOICES

logger = logging.getLogger("tts.engines.pocket")

_VARIANTS = {entry["id"]: entry for entry in POCKET_VARIANTS}


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()


class PocketEngine(BaseEngine):
    id = "pocket"
    name = "Pocket TTS"
    description = (
        "Kyutai Pocket TTS: 100M parameters, runs faster than realtime on CPU. "
        "26 official voices, 7 languages and voice cloning."
    )
    homepage = "https://github.com/kyutai-labs/pocket-tts"
    license = "MIT (code) / CC-BY (voices)"
    import_names = ["pocket_tts", "torch"]
    default_variant = "english"
    cloning = True
    install_specs = {
        "base": ["pocket-tts"],
        "notes": (
            "On Linux install CPU-only torch first to avoid multi-GB CUDA "
            "wheels: pip install pocket-tts --extra-index-url "
            "https://download.pytorch.org/whl/cpu"
        ),
    }
    custom_voice_types = [
        {
            "kind": "reference",
            "label": "Reference clip or .safetensors voice state",
            "accept": ".wav,.mp3,.flac,.ogg,.opus,.m4a,.safetensors",
            "help": (
                "Any 5-30 s clean sample. Exported `.safetensors` voice states "
                "load much faster than re-processing audio."
            ),
            "fields": [],
        }
    ]

    # ------------------------------------------------------------------
    def variants(self) -> list[dict[str, Any]]:
        return [
            {
                "id": variant["id"],
                "label": variant["label"],
                "description": (
                    f"{variant['language']} · {variant['layers']} layers"
                    + (" · higher quality, slower" if variant["high_quality"] else "")
                    + ("" if variant["id"] == "english" else
                       " · dedicated language model")
                ),
                "repo": "kyutai/pocket-tts",
                "size_hint": (
                    "~24 layers (larger download)" if variant["high_quality"]
                    else "~100M parameters"
                ),
                "download_required": True,
                "cloning": True,
                "load_options": [
                    option(
                        "device",
                        "Device",
                        "select",
                        "cpu",
                        ["cpu", "cuda", "auto"],
                        help_="Pocket TTS is CPU-first; GPU is optional.",
                    ),
                    option(
                        "quantize",
                        "int8 quantization",
                        "bool",
                        False,
                        help_="Dynamic int8 quantization (CPU only). Faster, slightly lower fidelity.",
                    ),
                    option(
                        "temperature",
                        "Sampling temperature",
                        "float",
                        None,
                        minimum=0.1,
                        maximum=1.5,
                        step=0.05,
                        help_="Default comes from the model config (0.3).",
                    ),
                    option(
                        "eos_threshold",
                        "EOS threshold",
                        "float",
                        None,
                        minimum=-8.0,
                        maximum=0.0,
                        step=0.1,
                        advanced=True,
                        help_="Lower ends sequences earlier.",
                    ),
                ],
                "gen_options": [],
            }
            for variant in POCKET_VARIANTS
        ]

    def voices(
        self, variant_id: str | None, custom_voices: list[Any] | None = None
    ) -> list[Voice]:
        target_lang = _VARIANTS.get(variant_id or self.default_variant, {}).get("lang")
        voices = []
        for entry in POCKET_VOICES:
            voices.append(
                Voice(
                    id=entry["id"],
                    name=entry["id"],
                    language=entry["language"],
                    lang_code=entry["lang"],
                    gender=entry["gender"],
                    description=entry["desc"],
                    variants=None,  # engineered voice states; usable with any variant
                    tags=["official"],
                    extra={
                        "flag": (
                            "🇫🇷" if entry["lang"] == "fr"
                            else "🇩🇪" if entry["lang"] == "de"
                            else "🇮🇹" if entry["lang"] == "it"
                            else "🇵🇹" if entry["lang"] == "pt"
                            else "🇪🇸" if entry["lang"] == "es"
                            else "🇬🇧"
                        ),
                        "recommended": entry["lang"] == target_lang,
                    },
                )
            )
        for custom in custom_voices or []:
            voices.append(
                Voice(
                    id=f"custom:{custom['id']}",
                    name=custom["name"],
                    language="Cloned",
                    lang_code="en",
                    gender=None,
                    description="Cloned reference voice",
                    custom=True,
                    path=custom.get("path"),
                    tags=["cloning"],
                    extra={"flag": "🧬"},
                )
            )
        return voices

    # ------------------------------------------------------------------
    def load(self, variant_id: str, options: dict[str, Any]) -> LoadedHandle:
        from pocket_tts import TTSModel

        variant_id = variant_id or self.default_variant
        if variant_id not in _VARIANTS:
            raise EngineError(f"Unknown Pocket TTS language '{variant_id}'")

        kwargs: dict[str, Any] = {"language": variant_id}
        quantize = bool(options.get("quantize", False))
        if quantize:
            kwargs["quantize"] = True
        temperature = options.get("temperature")
        if temperature not in (None, ""):
            kwargs["temp"] = float(temperature)
        eos_threshold = options.get("eos_threshold")
        if eos_threshold not in (None, ""):
            kwargs["eos_threshold"] = float(eos_threshold)

        device = (options.get("device") or "cpu").lower()
        if device == "cuda" and quantize:
            raise EngineError(
                "int8 quantization is only supported on CPU. Disable it or use CPU.",
                code="bad_options",
            )

        logger.info(
            "Loading Pocket TTS '%s' (device=%s, quantize=%s) - weights download "
            "on first use",
            variant_id,
            device,
            quantize,
        )
        model = TTSModel.load_model(**kwargs)
        if device == "cuda":
            import torch

            if not torch.cuda.is_available():
                raise EngineError(
                    "CUDA was requested but is not available.", code="device_unavailable"
                )
            model = model.to("cuda")

        actual_device = str(getattr(model, "device", device))
        handle = {
            "model": model,
            "voice_states": {},
            "variant": variant_id,
        }
        return LoadedHandle(
            engine_id=self.id,
            variant_id=variant_id,
            options={"device": device, **options},
            handle=handle,
            device=actual_device,
            sample_rate=int(model.sample_rate),
            meta={"variant": variant_id},
        )

    # ------------------------------------------------------------------
    def _voice_state(self, loaded: LoadedHandle, voice: VoiceRef, log) -> Any:
        from pocket_tts import export_model_state

        handle = loaded.handle
        model = handle["model"]
        cache_key = f"{loaded.variant_id}:{voice.kind}:{voice.value}"
        if cache_key in handle["voice_states"]:
            return handle["voice_states"][cache_key]

        source = voice.value
        cache_dir = (
            config.MODELS_DIR / "pocket_voices" / _slug(loaded.variant_id)
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        state_path = cache_dir / f"{_slug(voice.value)}.safetensors"

        if state_path.is_file():
            log(f"Loading cached voice state for '{voice.value}'")
            try:
                state = model.get_state_for_audio_prompt(str(state_path))
                handle["voice_states"][cache_key] = state
                return state
            except Exception as exc:  # stale / incompatible cache
                logger.warning("Cached voice state unusable (%s); rebuilding", exc)
                state_path.unlink(missing_ok=True)

        log(f"Preparing voice state for '{voice.value}' (first use may download)")
        state = model.get_state_for_audio_prompt(source)
        try:
            export_model_state(state, state_path)
            log(f"Cached voice state to {state_path.name}")
        except Exception as exc:  # pragma: no cover - cache is best effort
            logger.warning("Could not cache voice state: %s", exc)
        handle["voice_states"][cache_key] = state
        return state

    def generate(
        self,
        loaded: LoadedHandle,
        text: str,
        voice: VoiceRef,
        options: dict[str, Any],
        progress,
        cancelled,
    ) -> GenerationResult:
        progress(0.02, "Preparing voice")
        state = self._voice_state(loaded, voice, lambda message: progress(0.05, message))
        if cancelled():
            raise CancelledError("Cancelled during Pocket TTS generation")

        model = loaded.handle["model"]
        sample_rate = int(model.sample_rate)
        expected_samples = max(sample_rate, int(len(text) / 13.0 * sample_rate))
        parts: list[np.ndarray] = []

        progress(0.1, "Synthesizing")
        stream = model.generate_audio_stream(state, text)
        for chunk in stream:
            if cancelled():
                raise CancelledError("Cancelled during Pocket TTS generation")
            tensor = chunk.detach().to("cpu") if hasattr(chunk, "detach") else chunk
            array = np.asarray(tensor, dtype=np.float32).reshape(-1)
            parts.append(array)
            generated = sum(len(part) for part in parts)
            progress(0.1 + 0.85 * min(0.99, generated / expected_samples), None)

        if not parts:
            raise EngineError("Pocket TTS produced no audio for this input.")

        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        return GenerationResult(
            audio=audio,
            sample_rate=sample_rate,
            meta={"variant": loaded.variant_id},
        )
