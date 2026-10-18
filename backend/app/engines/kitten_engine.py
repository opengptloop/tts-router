"""Kitten TTS engine adapter.

Supports both model families shipped by ``pip install kittenml``:

* **KittenTTS 2** (1.7B speech LM): 47 built-in voices, 10 languages,
  voice cloning, expression tags and decoding presets.
* **KittenTTS 0.8 ONNX** (mini/micro/nano/nano-int8): 8 voices, speed control.

Docs: https://github.com/KittenML/KittenTTS
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
from .catalogs import (
    KITTEN_08_VOICES,
    KITTEN_LANGUAGES,
    KITTEN2_VOICES,
    KITTEN_VARIANTS,
)

logger = logging.getLogger("tts.engines.kitten")


@dataclass
class _Variant:
    id: str
    label: str
    family: str
    model_ids: list[str]
    cloning: bool


_VARIANTS = {entry["id"]: entry for entry in KITTEN_VARIANTS}



_LLM_LOAD_OPTIONS = [
    option(
        "device",
        "Device",
        "select",
        "cpu",
        ["cpu", "cuda", "auto"],
        help_="CPU by default; CUDA speeds it up when available.",
    ),
    option(
        "weights",
        "Weights",
        "select",
        "packed",
        ["packed", "emb4"],
        advanced=True,
        help_="'emb4' halves the download at a small quality cost.",
    ),
]
_ONNX_LOAD_OPTIONS = [
    option(
        "device",
        "Execution provider",
        "select",
        "cpu",
        ["cpu", "cuda"],
        help_="ONNX runtime provider. CUDA requires onnxruntime-gpu.",
    ),
]
_LLM_GEN_OPTIONS = [
    option(
        "preset",
        "Decoding preset",
        "select",
        "stable",
        ["stable", "expressive"],
        help_="'expressive' loosens sampling for livelier delivery.",
    ),
    option("temperature", "Temperature", "float", None, minimum=0.1, maximum=2.0,
           step=0.05, help_="Overrides the preset when set."),
    option("top_p", "Top P", "float", None, minimum=0.0, maximum=1.0, step=0.01),
    option("top_k", "Top K", "int", None, minimum=0, maximum=200, advanced=True,
           help_="0 disables top-k."),
    option("min_p", "Min P", "float", None, minimum=0.0, maximum=1.0, step=0.01,
           advanced=True),
    option("seed", "Seed", "int", None,
           help_="Seed the sampler for reproducible audio."),
    option("normalize", "Text normalization", "bool", True,
           help_="Expand numbers, dates and abbreviations (English-tuned)."),
    option("max_new_tokens", "Max tokens per chunk", "int", None, minimum=50,
           maximum=4000, advanced=True),
]
_ONNX_GEN_OPTIONS = [
    option("speed", "Speed", "float", 1.0, minimum=0.5, maximum=2.0, step=0.05),
    option("clean_text", "Text cleaning", "bool", True),
]


class KittenEngine(BaseEngine):
    id = "kitten"
    name = "Kitten TTS"
    description = (
        "KittenML family: the 1.7B KittenTTS 2 with voice cloning and 47 voices, "
        "plus the ultra-light 15M-80M ONNX models."
    )
    homepage = "https://github.com/KittenML/KittenTTS"
    license = "Apache-2.0 (code) / model-specific"
    import_names = ["kittenml", "torch"]
    default_variant = "kitten-tts-2"
    cloning = True
    install_specs = {"base": ["kittenml"]}
    custom_voice_types = [
        {
            "kind": "reference",
            "label": "Reference clip (5-30 s)",
            "accept": ".wav,.mp3,.flac,.ogg,.opus,.m4a",
            "help": (
                "Voice cloning with KittenTTS 2. A transcript is auto-detected "
                "with Whisper when not supplied."
            ),
            "fields": ["reference_text"],
        }
    ]

    # ------------------------------------------------------------------
    def variants(self) -> list[dict[str, Any]]:
        entries = []
        for variant in KITTEN_VARIANTS:
            is_llm = variant["family"] == "llm"
            entries.append(
                {
                    "id": variant["id"],
                    "label": variant["label"],
                    "description": variant["description"],
                    "repo": variant["model_ids"][0],
                    "size_hint": variant["size_hint"],
                    "download_required": True,
                    "cloning": variant["cloning"],
                    "load_options": _LLM_LOAD_OPTIONS if is_llm else _ONNX_LOAD_OPTIONS,
                    "gen_options": _LLM_GEN_OPTIONS if is_llm else _ONNX_GEN_OPTIONS,
                    "supports_expressions": is_llm,
                }
            )
        return entries

    def voices(
        self, variant_id: str | None, custom_voices: list[Any] | None = None
    ) -> list[Voice]:
        variant = _VARIANTS.get(variant_id or self.default_variant, {})
        if variant.get("family") == "llm":
            voices = []
            for voice in KITTEN2_VOICES:
                lang = voice.get("lang", "en")
                meta = KITTEN_LANGUAGES.get(lang, {"name": lang, "flag": "🏳️"})
                tags = ["cloning"]
                if "lang" in voice:
                    tags.append("multilingual")
                voices.append(
                    Voice(
                        id=voice["id"],
                        name=voice["id"],
                        language=meta["name"],
                        lang_code=lang,
                        gender=voice["gender"],
                        description=voice["desc"],
                        variants=["kitten-tts-2"],
                        tags=tags,
                        extra={"flag": meta["flag"]},
                    )
                )
        else:
            voices = [
                Voice(
                    id=name,
                    name=name,
                    language="English",
                    lang_code="en",
                    gender=gender,
                    description="KittenTTS 0.8 voice",
                    variants=[
                        entry["id"]
                        for entry in KITTEN_VARIANTS
                        if entry["family"] == "onnx"
                    ],
                    tags=["legacy"],
                    extra={"flag": "🇬🇧"},
                )
                for name, gender in KITTEN_08_VOICES
            ]
        for custom in custom_voices or []:
            voices.append(
                Voice(
                    id=f"custom:{custom['id']}",
                    name=custom["name"],
                    language="Cloned (KittenTTS 2)",
                    lang_code="en",
                    gender=None,
                    description="Cloned reference voice",
                    custom=True,
                    path=custom.get("path"),
                    variants=["kitten-tts-2"],
                    tags=["cloning"],
                    extra={"flag": "🧬"},
                )
            )
        return voices

    # ------------------------------------------------------------------
    def load(self, variant_id: str, options: dict[str, Any]) -> LoadedHandle:
        from kittenml import KittenTTS

        variant_id = variant_id or self.default_variant
        variant = _VARIANTS.get(variant_id)
        if variant is None:
            raise EngineError(f"Unknown Kitten variant '{variant_id}'")

        kwargs: dict[str, Any] = {
            "cache_dir": str(config.MODELS_DIR / "kitten"),
        }
        device = (options.get("device") or "cpu").lower()
        if variant["family"] == "llm":
            if device != "auto":
                kwargs["device"] = device
            weights = options.get("weights")
            if weights:
                kwargs["weights"] = weights
        else:
            kwargs["backend"] = "cuda" if device == "cuda" else "cpu"

        last_error: Exception | None = None
        model = None
        used_id = variant["model_ids"][0]
        for model_id in variant["model_ids"]:
            try:
                logger.info(
                    "Loading %s (repo=%s, options=%s) - weights download on first use",
                    variant["label"],
                    model_id,
                    kwargs,
                )
                model = KittenTTS(model_id, **kwargs)
                used_id = model_id
                break
            except Exception as exc:  # try the next repository id
                last_error = exc
                logger.warning("Failed to load %s: %s", model_id, exc)
        if model is None:
            raise EngineError(
                f"Could not load {variant['label']}: {last_error}",
                code="model_load_failed",
            )

        sample_rate = int(getattr(model, "sample_rate", 24000))
        handle = {"model": model, "family": variant["family"]}
        return LoadedHandle(
            engine_id=self.id,
            variant_id=variant_id,
            options={"device": device, **options},
            handle=handle,
            device=device,
            sample_rate=sample_rate,
            meta={"repo": used_id, "family": variant["family"]},
        )

    # ------------------------------------------------------------------
    def _tts2_voice_kwargs(
        self, voice: VoiceRef, options: dict[str, Any]
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if voice.kind == "file":
            kwargs["reference"] = voice.value
            reference_text = (
                options.get("reference_text")
                or voice.reference_text
            )
            if reference_text:
                kwargs["reference_text"] = reference_text
        else:
            kwargs["voice"] = voice.value

        if options.get("preset"):
            kwargs["preset"] = options["preset"]
        for key in ("temperature", "top_k", "top_p", "min_p"):
            value = options.get(key)
            if value not in (None, ""):
                kwargs[key] = value
        if options.get("normalize") is not None:
            kwargs["normalize"] = bool(options["normalize"])
        if options.get("max_new_tokens") not in (None, ""):
            kwargs["max_new_tokens"] = int(options["max_new_tokens"])
        if options.get("seed") not in (None, ""):
            kwargs["advanced"] = {"seed": int(options["seed"])}
        return kwargs

    def generate(
        self,
        loaded: LoadedHandle,
        text: str,
        voice: VoiceRef,
        options: dict[str, Any],
        progress,
        cancelled,
    ) -> GenerationResult:
        model = loaded.handle["model"]
        family = loaded.handle["family"]
        sample_rate = int(getattr(model, "sample_rate", 24000))
        progress(0.05, "Starting synthesis")

        if family == "llm":
            kwargs = self._tts2_voice_kwargs(voice, options)
            parts: list[np.ndarray] = []

            if hasattr(model, "generate_stream"):
                expected_seconds = max(1.0, len(text) / 14.0)

                def _collect_stream(stream) -> list[np.ndarray]:
                    collected: list[np.ndarray] = []
                    for chunk in stream:
                        if cancelled():
                            raise CancelledError("Cancelled during Kitten generation")
                        collected.append(np.asarray(chunk, dtype=np.float32).reshape(-1))
                        seconds = sum(len(c) for c in collected) / sample_rate
                        progress(
                            0.08 + 0.9 * min(0.99, seconds / expected_seconds),
                            None,
                        )
                    return collected

                try:
                    parts = _collect_stream(model.generate_stream(text, **kwargs))
                except TypeError:
                    parts = []

            if not parts:
                if cancelled():
                    raise CancelledError("Cancelled during Kitten generation")
                progress(0.5, "Synthesizing")
                audio = np.asarray(model.generate(text, **kwargs), dtype=np.float32)
                parts = [audio.reshape(-1)]
                progress(0.99, None)
        else:
            if voice.kind == "file":
                raise EngineError(
                    f"Voice cloning needs KittenTTS 2; '{loaded.variant_id}' is an "
                    "ONNX model without cloning support.",
                    code="cloning_not_supported",
                )
            kwargs = {"voice": voice.value}
            if options.get("speed") is not None:
                kwargs["speed"] = float(options["speed"])
            if options.get("clean_text") is not None:
                kwargs["clean_text"] = bool(options["clean_text"])
            if cancelled():
                raise CancelledError("Cancelled during Kitten generation")
            try:
                audio = model.generate(text, **kwargs)
            except TypeError:
                # Older kittenml releases had a different signature.
                audio = model.generate(text, voice=voice.value)
            parts = [np.asarray(audio, dtype=np.float32).reshape(-1)]
            progress(0.99, None)

        if not parts:
            raise EngineError("Kitten TTS produced no audio for this input.")

        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        return GenerationResult(
            audio=audio,
            sample_rate=sample_rate,
            meta={"family": family, "voice": voice.value if voice.kind == "builtin" else "cloned"},
        )
