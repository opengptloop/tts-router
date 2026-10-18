# TTS Studio — Backend

FastAPI backend that runs open-source text-to-speech models **locally**
(Kokoro, Kitten TTS, Pocket TTS and Piper), manages model downloads and
voices, streams logs over WebSocket and serves generated audio.

## Requirements

- Python 3.10 – 3.12 (Kokoro does not ship wheels for 3.13 yet)
- Linux, macOS or Windows; CUDA optional
- ~2 GB disk for the core install, more per model/voice you download

## Install

```bash
cd backend
python -m venv ../.venv && source ../.venv/bin/activate   # optional
pip install -e ".[all]"        # all four engines
# or pick engines individually:
pip install -e ".[piper]"      # only Piper (tiny, ONNX-based)
pip install -e ".[kokoro]"     # only Kokoro
```

CPU-only machines can avoid the multi-GB CUDA torch build:

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[all]"
```

## Run

```bash
python run.py                      # http://127.0.0.1:8000
python run.py --host 0.0.0.0 --port 9000
python run.py --reload             # dev auto-reload
```

Interactive API docs: <http://127.0.0.1:8000/docs>

If `frontend/dist` exists it is served at `/`, so a production build can run
behind this single process.

## Configuration

Copy `.env.example` for reference. All variables are optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `TTS_DATA_DIR` | `backend/data` | Models, voices, audio, logs |
| `TTS_HOST` / `TTS_PORT` | `127.0.0.1:8000` | Bind address |
| `TTS_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `TTS_PIPER_CATALOG_TTL` | `604800` | Piper catalogue cache (seconds) |

Everything downloaded (Hugging Face weights, Piper voices, generated audio)
stays inside `TTS_DATA_DIR`.

## API overview

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | Liveness probe |
| `GET /api/models` | Engines, variants, load state |
| `POST /api/models/{id}/install` | pip-install an engine (background job) |
| `POST /api/models/{id}/load` / `/unload` | Load/unload a variant (job) |
| `GET /api/engines/{id}/voices` | Voice list for an engine |
| `GET/POST /api/engines/piper/catalog` | Piper catalogue / refresh |
| `POST /api/engines/piper/voices/{key}/download` | Download a Piper voice (job) |
| `POST /api/generate` | Synthesize (job) |
| `GET /api/jobs/{id}` | Job status/progress/logs |
| `GET /api/audio/{file}` | Serve generated audio |
| `GET /api/history` | Recent generations |
| `GET /api/system/status` | CPU, RAM, disk, GPU, cache usage |
| `GET /api/logs`, `DELETE /api/logs` | Log tail / clear |
| `WS /ws/logs` | Live log stream |

Background work (installs, downloads, synthesis) runs through a small job
manager; the frontend polls `GET /api/jobs/{id}` for progress.

## Data layout

```
backend/data/
├── hf_cache/        # Hugging Face downloads (Kokoro/Kitten/Pocket)
├── models/          # engine-specific weight caches (e.g. Piper, Kitten)
├── piper_voices/    # downloaded Piper .onnx + config files
├── custom_voices/   # user-uploaded voices
├── audio/           # generated WAV files
├── previews/        # cached voice previews
├── history.json     # generation history
└── logs/            # rotating text logs
```
