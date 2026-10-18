"""TTS engine adapters."""

from . import catalogs  # noqa: F401
from .base import (  # noqa: F401
    BaseEngine,
    EngineError,
    GenerationResult,
    LoadedHandle,
    Voice,
    VoiceRef,
    option,
)
from .kokoro_engine import KokoroEngine  # noqa: F401
from .kitten_engine import KittenEngine  # noqa: F401
from .piper_engine import PiperEngine  # noqa: F401
from .pocket_engine import PocketEngine  # noqa: F401

__all__ = [
    "BaseEngine",
    "EngineError",
    "GenerationResult",
    "LoadedHandle",
    "Voice",
    "VoiceRef",
    "option",
    "KokoroEngine",
    "KittenEngine",
    "PocketEngine",
    "PiperEngine",
]
