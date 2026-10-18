# TTS Studio

A local-first web studio for open-source text-to-speech. Pick an engine, pick
a voice (or clone one), type your text and get audio — all running on your own
machine, with no API keys and no data leaving your computer.

![stack](https://img.shields.io/badge/backend-FastAPI-009688)
![stack](https://img.shields.io/badge/frontend-React%2019-61dafb)
![stack](https://img.shields.io/badge/engines-Kokoro%20·%20Kitten%20·%20Pocket%20·%20Piper-7c5cff)

## Features

- **Four engines in one UI** — Kokoro-82M, KittenTTS 2 + 0.8 ONNX models,
  Pocket TTS and Piper, with per-engine variants and generation options.
- **Voice management** — 300+ built-in voices, searchable and filterable by
  language, gender and quality; on-demand downloads with progress; custom
  voice uploads (Kokoro tensors, Kitten/Pocket reference clips, Piper ONNX).
- **Voice cloning** — reference-clip cloning with KittenTTS 2 (Whisper
  auto-transcription when no transcript is given).
- **Studio workflow** — single or batch (one clip per line) synthesis, live
  job progress, inline previews, result player, downloadable WAV history.
- **Models & Config page** — install engines with pip in the background,
  load/unload variants, browse the full Piper catalogue, monitor CPU/RAM/disk/GPU.
- **Live logs** — backend logs streamed to the browser over WebSocket.
- **Dark & light theme**, responsive layout, no telemetry.

## Engines

| Engine | Family | Voices | Languages | Cloning |
| --- | --- | --- | --- | --- |
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | StyleTTS2 | 54 | 9 | via custom `.pt` tensors |
| [KittenTTS 2](https://github.com/KittenML/KittenTTS) | 1.7B speech LM | 47 | 10 | yes (reference clip) |
| KittenTTS 0.8 | ONNX (15–80M) | 8 | English | no |
| [Pocket TTS](https://github.com/kyutai-labs/pocket-tts) | 100M LM | 26 | 6 | via exported voice states |
| [Piper](https://github.com/OHF-Voice/piper1-gpl) | VITS/ONNX | 177 | 40+ | — |

Models are downloaded on first use and cached locally. Only engines whose
Python package is installed show as ready; the rest can be installed from the
Models page.

## Requirements

- Python 3.10 – 3.12 (Kokoro has no 3.13 wheels yet)
- Node.js 20+ (only for building/serving the frontend yourself)
- Optional NVIDIA GPU with CUDA for faster synthesis

## Quickstart

### 1. Backend

```bash
cd backend
python -m venv ../.venv && source ../.venv/bin/activate
pip install -e ".[all]"        # or ".[piper]" for a lightweight start
python run.py                  # http://127.0.0.1:8000
```

CPU-only tip: install torch first from the CPU wheel index to avoid pulling
multi-GB CUDA libraries (see `backend/requirements.txt`).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173, proxies /api to :8000
```

For a single-process deployment, build the frontend and start only the backend:

```bash
npm run build                  # writes frontend/dist
cd ../backend && python run.py # serves the built UI at http://127.0.0.1:8000
```

### 3. Use it

1. Open the **Models & Config** page and install the engine(s) you want.
2. Load a model variant (weights download on first load).
3. Go to the **Studio**, choose an engine/voice, type text and hit Generate.
4. Watch **Logs** for live backend activity.

## Project layout

```
backend/    FastAPI app, engine adapters, job manager, log bus
  app/engines/   kokoro / kitten / pocket / piper adapters + catalogs
  app/routers/   system, models, voices, generate endpoints
frontend/   React 19 + Vite single-page app
  src/pages/     Studio, Models & Config, Logs
  src/components/voice picker, modals, toasts, primitives
```

Runtime data (models, voices, audio, logs) lives in `backend/data/` — see
`backend/README.md` for the full API reference and configuration variables.

## Notes

- Voices and weights belong to their upstream projects; licences vary per
  model (Kokoro: Apache-2.0, KittenTTS code: Apache-2.0, Pocket TTS:
  CC-BY-4.0, Piper voices: per-voice). Check the upstream model cards before
  commercial use.
- Everything is stored and computed locally; the only network calls are model
  and voice downloads from Hugging Face.
