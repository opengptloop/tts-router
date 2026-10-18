"""Application paths and settings.

All runtime data (models, downloaded voices, generated audio, logs) is kept
inside ``backend/data`` by default so that everything stays local. Override
with the ``TTS_DATA_DIR`` environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

APP_NAME = "TTS Studio"
APP_VERSION = "1.0.0"

DATA_DIR = Path(os.environ.get("TTS_DATA_DIR", BASE_DIR / "data")).resolve()

# Keep every Hugging Face download (Kokoro weights, Kitten weights, Pocket
# weights and voices) inside the local data directory. Must be set before
# huggingface_hub is imported anywhere.
HF_CACHE_DIR = DATA_DIR / "hf_cache"
os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR))

MODELS_DIR = DATA_DIR / "models"
PIPER_VOICES_DIR = DATA_DIR / "piper_voices"
OUTPUTS_DIR = DATA_DIR / "audio"
PREVIEWS_DIR = DATA_DIR / "previews"
CUSTOM_VOICES_DIR = DATA_DIR / "custom_voices"
LOGS_DIR = DATA_DIR / "logs"
API_AUDIO_DIR = DATA_DIR / "api_audio"

HISTORY_FILE = DATA_DIR / "history.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
PIPER_CATALOG_FILE = DATA_DIR / "piper_catalog.json"
API_KEYS_FILE = DATA_DIR / "api_keys.json"
API_CONFIG_FILE = DATA_DIR / "api_config.json"

HOST = os.environ.get("TTS_HOST", "127.0.0.1")
PORT = int(os.environ.get("TTS_PORT", "8000"))

# Comma separated origins; "*" by default so the Vite dev server and
# reverse-proxied deployments both work out of the box.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("TTS_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

# Seconds before the Piper voice catalogue is considered stale and re-fetched.
PIPER_CATALOG_TTL = int(os.environ.get("TTS_PIPER_CATALOG_TTL", str(7 * 24 * 3600)))

PIPER_CATALOG_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
)
PIPER_VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

KOKORO_REPO = "hexgrad/Kokoro-82M"
KOKORO_SAMPLE_RATE = 24000


def ensure_dirs() -> None:
    for directory in (
        DATA_DIR,
        HF_CACHE_DIR,
        MODELS_DIR,
        PIPER_VOICES_DIR,
        OUTPUTS_DIR,
        PREVIEWS_DIR,
        CUSTOM_VOICES_DIR,
        LOGS_DIR,
        API_AUDIO_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


ensure_dirs()
