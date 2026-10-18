"""Coordinates engines: install, load/unload, voice resolution, generation.

Multiple engines can be loaded at the same time; each engine has its own
re-entrant lock so heavyweight work on one engine never blocks another.
"""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from . import config
from .engines.base import BaseEngine, EngineError, GenerationResult, LoadedHandle, VoiceRef
from .engines.catalogs import KOKORO_LANG_BY_VOICE
from .storage import CUSTOM_VOICES

logger = logging.getLogger("tts.manager")


class ModelManager:
    def __init__(self, engines: list[BaseEngine]) -> None:
        self.engines: dict[str, BaseEngine] = {engine.id: engine for engine in engines}
        self._runtimes: dict[str, LoadedHandle] = {}
        self._load_options: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, threading.RLock] = {
            engine.id: threading.RLock() for engine in engines
        }
        # Engines pip-installed while this process was already running: their
        # packages may not be importable in this process until a restart.
        self._installed_at_runtime: set[str] = set()

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def engine(self, engine_id: str) -> BaseEngine:
        engine = self.engines.get(engine_id)
        if engine is None:
            raise EngineError(f"Unknown engine '{engine_id}'", code="unknown_engine")
        return engine

    def runtime(self, engine_id: str) -> LoadedHandle | None:
        return self._runtimes.get(engine_id)

    def lock(self, engine_id: str) -> threading.RLock:
        return self._locks[engine_id]

    def require_installed(self, engine_id: str) -> BaseEngine:
        engine = self.engine(engine_id)
        if not engine.installed():
            packages = " ".join(engine.installed_packages())
            raise EngineError(
                f"{engine.name} is not installed. Install it from the Models page "
                f"or run: pip install {packages}",
                code="not_installed",
            )
        return engine

    # ------------------------------------------------------------------
    # Variants / cache status
    # ------------------------------------------------------------------
    def variant_cache_status(self, engine: BaseEngine, variant: dict[str, Any]) -> str:
        """Best-effort check whether weights already live in the local cache."""
        repo = variant.get("repo")
        if not repo:
            return "unknown"
        hub = config.HF_CACHE_DIR / "hub"
        folder = hub / f"models--{repo.replace('/', '--')}"
        if not folder.is_dir():
            return "not_downloaded"
        snapshots = folder / "snapshots"
        if snapshots.is_dir() and any(snapshots.iterdir()):
            return "downloaded"
        return "not_downloaded"

    def variants_with_status(self, engine_id: str) -> list[dict[str, Any]]:
        engine = self.engine(engine_id)
        variants = []
        for variant in engine.variants():
            enriched = dict(variant)
            enriched["cache_status"] = (
                self.variant_cache_status(engine, variant)
                if engine.installed()
                else "engine_not_installed"
            )
            variants.append(enriched)
        return variants

    # ------------------------------------------------------------------
    # Load / unload
    # ------------------------------------------------------------------
    def default_load_options(
        self, engine: BaseEngine, variant_id: str | None = None
    ) -> dict[str, Any]:
        variants = engine.variants()
        variant = next(
            (v for v in variants if v["id"] == (variant_id or engine.default_variant)),
            variants[0] if variants else None,
        )
        options: dict[str, Any] = {}
        for spec in (variant or {}).get("load_options", []):
            if spec.get("default") is not None:
                options[spec["key"]] = spec["default"]
        return options

    def load_model(
        self,
        engine_id: str,
        variant_id: str | None,
        options: dict[str, Any] | None = None,
        progress: Callable[[float, str | None], None] | None = None,
    ) -> LoadedHandle:
        engine = self.require_installed(engine_id)
        variant_id = variant_id or engine.default_variant
        with self._locks[engine_id]:
            return self._load_locked(engine, variant_id, options or {}, progress)

    def _load_locked(
        self,
        engine: BaseEngine,
        variant_id: str,
        options: dict[str, Any],
        progress: Callable[[float, str | None], None] | None = None,
    ) -> LoadedHandle:
        current = self._runtimes.get(engine.id)
        if current is not None and current.variant_id == variant_id:
            return current
        if current is not None:
            logger.info(
                "Unloading %s variant '%s' before loading '%s'",
                engine.id,
                current.variant_id,
                variant_id,
            )
            self._unload_locked(engine)
        if progress:
            progress(0.05, f"Loading {engine.name} ({variant_id})")
        started = time.time()
        try:
            handle = engine.load(variant_id, options)
        except ImportError as exc:
            if engine.id in self._installed_at_runtime:
                raise EngineError(
                    f"{engine.name} was installed while the backend was already "
                    "running, so this process cannot import it yet. Restart the "
                    f"backend, then load the model again. Original error: {exc}",
                    code="restart_required",
                ) from exc
            raise
        self._installed_at_runtime.discard(engine.id)
        self._runtimes[engine.id] = handle
        self._load_options[engine.id] = dict(options)
        logger.info(
            "%s variant '%s' loaded on %s in %.1fs",
            engine.name,
            variant_id,
            handle.device,
            time.time() - started,
        )
        if progress:
            progress(1.0, "Loaded")
        return handle

    def unload_model(self, engine_id: str, timeout: float = 15.0) -> bool:
        engine = self.engine(engine_id)
        acquired = self._locks[engine_id].acquire(timeout=timeout)
        if not acquired:
            raise EngineError(
                f"{engine.name} is busy (generation in progress). Try again shortly.",
                code="engine_busy",
            )
        try:
            return self._unload_locked(engine)
        finally:
            self._locks[engine_id].release()

    def _unload_locked(self, engine: BaseEngine) -> bool:
        runtime = self._runtimes.pop(engine.id, None)
        if runtime is None:
            return False
        try:
            engine.unload(runtime)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Error while unloading %s: %s", engine.id, exc)
        logger.info("%s variant '%s' unloaded", engine.name, runtime.variant_id)
        return True

    # ------------------------------------------------------------------
    # Voice resolution
    # ------------------------------------------------------------------
    def resolve_voice(self, engine_id: str, voice_choice: str | None) -> VoiceRef:
        if not voice_choice:
            raise EngineError("Please select a voice.", code="voice_required")
        if voice_choice.startswith("custom:"):
            voice_id = voice_choice.split(":", 1)[1]
            custom = CUSTOM_VOICES.get(engine_id, voice_id)
            if custom is None or not custom.primary_path().is_file():
                raise EngineError(
                    "Custom voice not found. Re-upload it in the Studio.",
                    code="voice_not_found",
                )
            return VoiceRef(
                kind="file",
                value=str(custom.primary_path()),
                language=custom.language,
                reference_text=custom.reference_text,
            )
        # Built-in voice id (Kokoro/kitten/pocket voice name or Piper key)
        language = None
        if engine_id == "kokoro":
            language = KOKORO_LANG_BY_VOICE.get(voice_choice)
        return VoiceRef(kind="builtin", value=voice_choice, language=language)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(
        self,
        engine_id: str,
        variant_id: str | None,
        voice_choice: str | None,
        text: str,
        options: dict[str, Any],
        progress: Callable[[float, str | None], None],
        cancelled: Callable[[], bool],
    ) -> tuple[LoadedHandle, GenerationResult]:
        engine = self.require_installed(engine_id)
        if not text or not text.strip():
            raise EngineError("Text is empty.", code="empty_text")
        voice = self.resolve_voice(engine_id, voice_choice)
        variant_id = variant_id or engine.default_variant

        with self._locks[engine_id]:
            runtime = self._runtimes.get(engine_id)
            if runtime is None or runtime.variant_id != variant_id:
                load_options = self._load_options.get(
                    engine_id, self.default_load_options(engine, variant_id)
                )
                runtime = self._load_locked(
                    engine,
                    variant_id,
                    load_options,
                    progress=lambda fraction, message: progress(
                        fraction * 0.1, message
                    ),
                )
            if cancelled():
                from .jobs import CancelledError

                raise CancelledError("Cancelled before generation")

            def engine_progress(fraction: float, message: str | None) -> None:
                progress(0.1 + 0.9 * max(0.0, min(1.0, fraction)), message)

            result = engine.generate(
                runtime, text, voice, options, engine_progress, cancelled
            )
        return runtime, result

    # ------------------------------------------------------------------
    # Engine installation (pip)
    # ------------------------------------------------------------------
    def installable_specs(self, engine_id: str) -> dict[str, dict[str, Any]]:
        engine = self.engine(engine_id)
        specs: dict[str, dict[str, Any]] = {
            "base": {
                "label": f"Install {engine.name}",
                "packages": engine.install_specs.get("base", []),
            }
        }
        for key, extra in (engine.install_specs.get("extras") or {}).items():
            specs[key] = {
                "label": extra.get("label", key),
                "packages": extra.get("packages", []),
            }
        return specs

    def install_engine(
        self,
        engine_id: str,
        spec_key: str,
        log: Callable[[str], None],
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        engine = self.engine(engine_id)
        specs = self.installable_specs(engine_id)
        spec = specs.get(spec_key)
        if spec is None:
            raise EngineError(
                f"Unknown install target '{spec_key}' for {engine.name}",
                code="unknown_spec",
            )
        packages = spec["packages"]
        if not packages:
            raise EngineError("Nothing to install for this target.", code="bad_spec")

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            *packages,
        ]
        log(f"Running: {' '.join(command)}")
        env = {**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1"}
        process = subprocess.Popen(
            command,
            cwd=str(config.BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                if cancelled():
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:  # pragma: no cover
                        process.kill()
                    from .jobs import CancelledError

                    raise CancelledError("Install cancelled")
                line = line.rstrip("\n")
                if line:
                    log(line)
            code = process.wait()
        finally:
            if process.poll() is None:  # pragma: no cover
                process.kill()
        if code != 0:
            raise EngineError(
                f"pip install exited with code {code}. See the job log for details.",
                code="install_failed",
            )
        importlib.invalidate_caches()
        installed = engine.installed()
        if installed:
            self._installed_at_runtime.add(engine_id)
            log(
                "Install finished. Restart the backend before loading this "
                "engine: packages installed into a running process often "
                "cannot be imported until the process is restarted."
            )
        else:
            log("Install finished, but the engine is still not importable.")
        return {
            "packages": packages,
            "installed": installed,
            "restart_required": engine_id in self._installed_at_runtime,
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for engine_id, engine in self.engines.items():
            runtime = self._runtimes.get(engine_id)
            info = engine.describe()
            info.update(
                {
                    "loaded": runtime is not None,
                    "loaded_variant": runtime.variant_id if runtime else None,
                    "loaded_at": runtime.loaded_at if runtime else None,
                    "device": runtime.device if runtime else None,
                    "sample_rate": runtime.sample_rate if runtime else None,
                    "load_options": runtime.options if runtime else None,
                    "meta": runtime.meta if runtime else None,
                    "restart_required": engine_id in self._installed_at_runtime,
                }
            )
            if engine_id == "piper" and runtime is not None:
                sessions = runtime.handle.get("sessions", {})
                info["loaded_voices"] = [key.split(":", 1)[1] for key in sessions]
            result[engine_id] = info
        return result


def build_manager() -> ModelManager:
    from .engines import KittenEngine, KokoroEngine, PiperEngine, PocketEngine

    return ModelManager([KokoroEngine(), KittenEngine(), PocketEngine(), PiperEngine()])


MANAGER: ModelManager | None = None


def get_manager() -> ModelManager:
    global MANAGER
    if MANAGER is None:
        MANAGER = build_manager()
    return MANAGER
