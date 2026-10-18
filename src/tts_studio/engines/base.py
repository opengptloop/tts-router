"""Engine adapter interface shared by Kokoro / Kitten / Pocket / Piper."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

logger = logging.getLogger("tts.engines")


class EngineError(RuntimeError):
    """Raised for user-facing engine failures (missing model, bad options...)."""

    def __init__(self, message: str, code: str = "engine_error") -> None:
        super().__init__(message)
        self.code = code


def option(
    key: str,
    label: str,
    type_: str = "float",
    default: Any = None,
    choices: list[Any] | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    help_: str = "",
    advanced: bool = False,
) -> dict[str, Any]:
    """Describe a load/generation option so the frontend can render a form."""
    return {
        "key": key,
        "label": label,
        "type": type_,
        "default": default,
        "choices": choices,
        "min": minimum,
        "max": maximum,
        "step": step,
        "help": help_,
        "advanced": advanced,
    }


@dataclass
class Voice:
    id: str
    name: str
    language: str  # human readable, e.g. "American English"
    lang_code: str | None = None
    gender: str | None = None  # "female" | "male" | None
    description: str = ""
    grade: str | None = None
    tags: list[str] = field(default_factory=list)
    variants: list[str] | None = None  # variant ids this voice works with
    speaker_count: int = 1
    speakers: list[dict[str, Any]] | None = None
    size_bytes: int | None = None
    downloaded: bool | None = None
    custom: bool = False
    path: str | None = None  # for custom voices
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "lang_code": self.lang_code,
            "gender": self.gender,
            "description": self.description,
            "grade": self.grade,
            "tags": self.tags,
            "variants": self.variants,
            "speaker_count": self.speaker_count,
            "speakers": self.speakers or [],
            "size_bytes": self.size_bytes,
            "downloaded": self.downloaded,
            "custom": self.custom,
            "extra": self.extra,
        }


@dataclass
class VoiceRef:
    kind: str  # "builtin" | "file"
    value: str  # builtin voice id/name or local file path
    voice: Voice | None = None
    language: str | None = None
    reference_text: str | None = None


ProgressFn = Callable[[float, str | None], None]
CancelFn = Callable[[], bool]


@dataclass
class GenerationResult:
    audio: np.ndarray
    sample_rate: int
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadedHandle:
    engine_id: str
    variant_id: str
    options: dict[str, Any]
    handle: Any
    loaded_at: float = field(default_factory=time.time)
    device: str = "cpu"
    sample_rate: int = 24000
    meta: dict[str, Any] = field(default_factory=dict)


class BaseEngine:
    """Common behaviour for all engines."""

    id: str = ""
    name: str = ""
    description: str = ""
    homepage: str = ""
    license: str = ""
    install_specs: dict[str, list[str]] = {}
    default_variant: str = ""
    cloning: bool = False
    custom_voice_types: list[dict[str, str]] = []
    import_names: list[str] = []

    # ------------------------------------------------------------------
    # Installation / introspection
    # ------------------------------------------------------------------
    def installed(self) -> bool:
        return all(
            importlib.util.find_spec(name) is not None for name in self.import_names
        )

    def version(self) -> str | None:
        if not self.installed():
            return None
        for package in self.installed_packages():
            for name in (package.split("[")[0], self.id):
                try:
                    return importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    continue
        return None

    def installed_packages(self) -> list[str]:
        return self.install_specs.get("base", [])

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------
    def variants(self) -> list[dict[str, Any]]:
        return []

    def voices(
        self, variant_id: str | None, custom_voices: list[Any] | None = None
    ) -> list[Voice]:
        return []

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------
    def load(self, variant_id: str, options: dict[str, Any]) -> LoadedHandle:
        raise NotImplementedError

    def unload(self, loaded: LoadedHandle) -> None:
        """Release the handle. Best effort - used for logs/cleanup."""
        handle = loaded.handle
        try:
            if hasattr(handle, "to"):
                handle.to("cpu")  # type: ignore[operator]
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            import gc

            gc.collect()
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(
        self,
        loaded: LoadedHandle,
        text: str,
        voice: VoiceRef,
        options: dict[str, Any],
        progress: ProgressFn,
        cancelled: CancelFn,
    ) -> GenerationResult:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "homepage": self.homepage,
            "license": self.license,
            "installed": self.installed(),
            "version": self.version() if self.installed() else None,
            "install_specs": self.install_specs,
            "default_variant": self.default_variant,
            "cloning": self.cloning,
            "custom_voice_types": self.custom_voice_types,
            "installed_packages": self.installed_packages(),
        }
