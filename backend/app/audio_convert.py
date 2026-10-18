"""Audio rendering for the OpenAI-compatible speech endpoint.

Engines return float PCM at their native sample rate. The public API can
deliver ``wav``, ``flac`` and ``pcm`` directly through soundfile, while
``mp3``, ``opus`` and ``aac`` are transcoded with ffmpeg when available.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config

logger = logging.getLogger("tts.openai.audio")


class AudioFormatError(RuntimeError):
    """Raised when a requested response format cannot be produced."""

    def __init__(self, message: str, code: str = "format_unavailable") -> None:
        super().__init__(message)
        self.code = code


FFMPEG = shutil.which("ffmpeg")

MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",  # raw 16-bit little-endian samples, no header
}

EXTENSIONS = {
    "mp3": ".mp3",
    "opus": ".opus",
    "aac": ".aac",
    "flac": ".flac",
    "wav": ".wav",
    "pcm": ".pcm",
}

# ffmpeg output args per container/format.
FFMPEG_ARGS = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "128k", "-f", "mp3"],
    "opus": ["-c:a", "libopus", "-b:a", "64k", "-f", "ogg"],
    "aac": ["-c:a", "aac", "-b:a", "128k", "-f", "adts"],
}


def formats_available() -> dict[str, bool]:
    """Which response formats can currently be produced."""
    return {
        "mp3": FFMPEG is not None,
        "opus": FFMPEG is not None,
        "aac": FFMPEG is not None,
        "flac": True,
        "wav": True,
        "pcm": True,
    }


def _ensure_workdir() -> Path:
    config.API_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    return config.API_AUDIO_DIR


def _write_wav(audio: np.ndarray, sample_rate: int, target: Path) -> None:
    samples = np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0)
    sf.write(str(target), samples, sample_rate, subtype="PCM_16")


def _ffmpeg_transcode(source: Path, fmt: str, target: Path) -> None:
    if FFMPEG is None:
        raise AudioFormatError(
            f"response_format '{fmt}' requires the ffmpeg binary on the host, "
            "but none was found. Install ffmpeg or use 'wav', 'flac' or 'pcm'.",
            code="format_unavailable",
        )
    command = [
        FFMPEG,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(source),
        *FFMPEG_ARGS[fmt],
        str(target),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioFormatError(
            f"Transcoding to '{fmt}' timed out.", code="transcode_timeout"
        ) from exc
    if result.returncode != 0 or not target.is_file():
        detail = (result.stderr or "").strip().splitlines()
        message = detail[-1] if detail else f"ffmpeg exited with {result.returncode}"
        raise AudioFormatError(
            f"Could not transcode audio to '{fmt}': {message}",
            code="transcode_failed",
        )


def render_audio(
    audio: np.ndarray,
    sample_rate: int,
    fmt: str,
) -> tuple[Path, str]:
    """Write ``audio`` in the requested format inside the API audio dir.

    Returns ``(path, media_type)``. The caller is responsible for scheduling
    :func:`cleanup_paths` with the returned files after the response is sent.
    """
    fmt = (fmt or "wav").lower()
    if fmt not in MEDIA_TYPES:
        raise AudioFormatError(
            f"Unknown response_format '{fmt}'. Supported formats: "
            + ", ".join(MEDIA_TYPES),
            code="invalid_response_format",
        )

    workdir = _ensure_workdir()
    stem = f"api_{uuid.uuid4().hex[:16]}"
    wav_path = workdir / f"{stem}.wav"
    out_path = workdir / f"{stem}{EXTENSIONS[fmt]}"

    _write_wav(audio, sample_rate, wav_path)

    if fmt == "wav":
        out_path = wav_path
    elif fmt == "pcm":
        samples, _ = sf.read(str(wav_path), dtype="int16")
        out_path.write_bytes(np.asarray(samples, dtype=np.int16).tobytes())
        wav_path.unlink(missing_ok=True)
    elif fmt == "flac":
        samples = np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0)
        sf.write(str(out_path), samples, sample_rate, format="FLAC", subtype="PCM_16")
        wav_path.unlink(missing_ok=True)
    else:
        _ffmpeg_transcode(wav_path, fmt, out_path)
        wav_path.unlink(missing_ok=True)

    return out_path, MEDIA_TYPES[fmt]


def cleanup_paths(*paths: Path | None) -> None:
    """Best-effort removal of temporary API audio files."""
    for path in paths:
        if not path:
            continue
        try:
            if Path(path).is_file():
                Path(path).unlink()
        except OSError:  # pragma: no cover - best effort
            logger.debug("Could not remove %s", path)


def prune_old_files(max_age_s: int = 3600) -> None:
    """Remove leftover API audio older than ``max_age_s`` (crash safety net)."""
    workdir = config.API_AUDIO_DIR
    if not workdir.is_dir():
        return
    import time

    now = time.time()
    for path in workdir.glob("api_*"):
        try:
            if now - path.stat().st_mtime > max_age_s:
                path.unlink()
        except OSError:  # pragma: no cover
            continue
