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
- **OpenAI-compatible speech API** — one endpoint, one base URL, zero client
  configuration. Configure the TTS model once in the UI, then send plain
  text from any OpenAI-compatible client (see the full reference below).
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
- Optional `ffmpeg` binary — only needed for the `mp3`, `opus` and `aac`
  output formats (`wav`, `flac` and `pcm` always work)

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
npm run dev                    # http://localhost:5173, proxies /api and /v1 to :8000
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

---

## OpenAI-compatible speech API

TTS Studio exposes a drop-in, OpenAI-compatible speech endpoint with a
**single base URL** and **one endpoint**. The flow is intentionally simple:

> **The server owns the configuration. The client just sends text.**

1. **You** (the administrator) pick the TTS model, voice and defaults **once**
   on the in-app **API** page and hit Save. Only installed engines can be
   selected, and for Piper only downloaded (installed) voices are listed.
2. **Clients** POST text to `/v1/audio/speech`. They never pick a model, a
   voice, or any other setting.
3. **Audio** comes back as a streamed binary file in the format you asked for.

There are no model mappings and no client-side setup beyond the base URL.
API keys are **optional**: the endpoint is open by default, and you can lock
it down with a single toggle if you ever need to.

### Base URL

Everything lives under one prefix — your server origin plus `/v1`:

| Deployment | Base URL |
| --- | --- |
| Default backend | `http://localhost:8000/v1` |
| Custom host/port | `http://<host>:<port>/v1` |
| Behind a reverse proxy | `https://<your-domain>/v1` |
| Frontend dev server | `http://localhost:5173/v1` (proxied to the backend) |

### Authentication — optional by default

The API starts in **open mode**: anyone who can reach the server may call it,
no key required. Keys exist if you want to lock things down or track usage.

| Mode | Behaviour |
| --- | --- |
| **Open** (default, `require_api_key: false`) | No header needed. If a valid key is sent anyway, it still gets usage stats and rate limits; unknown/placeholder keys are tolerated (so OpenAI SDKs that insist on a key keep working). |
| **Required** (`require_api_key: true`) | A valid key must be sent as `Authorization: Bearer sk-tts-...` (or an `api-key: <key>` header). Missing or wrong keys get `401 invalid_api_key`. |

Keys are created on the **API** page (or via the admin endpoints below). They
look like `sk-tts-<48 hex chars>`, can be named, rate-limited per minute,
revoked and deleted, and report usage counts.

### `POST /v1/audio/speech`

The only endpoint clients ever need.

#### Request body

```json
{
  "input": "Today is a wonderful day!",
  "output": "mp3"
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `input` | string **or** array of strings | yes | The text to synthesize. An array is joined with newlines into one clip. Maximum length is the server's `max_input_chars` (default 4096). |
| `output` | string | no | Audio format: `mp3`, `opus`, `aac`, `flac`, `wav`, `pcm`. Falls back to the server's default format (`mp3` unless changed). |
| `response_format` | string | no | OpenAI-compatible alias for `output`. If both are sent, `output` wins. |
| `model` | string | — | **Accepted but ignored.** Send it (e.g. `"tts-1"`) only because some SDKs require a value. |
| `voice` | string | — | **Accepted but ignored.** The server-configured voice always wins. |
| `speed` | number | — | **Accepted but ignored.** Speed is a server-side setting (0.25 – 4.0). |

Unknown extra fields are ignored, exactly like the OpenAI API — existing
OpenAI-shaped clients work unchanged. That's the whole request: **`input`**
plus, optionally, **`output`**.

#### Response

The audio bytes, streamed straight from disk with no intermediate buffering:

| Header | Meaning |
| --- | --- |
| `Content-Type` | Media type of the chosen format (e.g. `audio/mpeg`) |
| `Content-Disposition` | `inline; filename="speech_<timestamp>.<ext>"` |
| `X-Sample-Rate` | Engine sample rate in Hz (e.g. `22050` for Piper) |
| `X-Model` | Engine that rendered the audio (e.g. `piper`) |
| `X-Voice` | Voice that rendered the audio |

### Output formats

| Format | Media type | Rendered by | Notes |
| --- | --- | --- | --- |
| `mp3` *(default)* | `audio/mpeg` | ffmpeg (libmp3lame) | 128 kbps |
| `opus` | `audio/ogg` | ffmpeg (libopus) | 64 kbps, Opus in Ogg container |
| `aac` | `audio/aac` | ffmpeg (aac) | 128 kbps, ADTS stream |
| `flac` | `audio/flac` | soundfile | lossless |
| `wav` | `audio/wav` | soundfile | 16-bit PCM |
| `pcm` | `audio/pcm` | soundfile | raw 16-bit little-endian samples, **no header**; use `X-Sample-Rate` to play it back correctly |

`mp3`, `opus` and `aac` require an `ffmpeg` binary on the host; `wav`, `flac`
and `pcm` are always available. If ffmpeg is missing, requesting a
ffmpeg-only format returns `400 format_unavailable` listing what *is*
available. The engine's native sample rate is used for every format.

### Errors

Errors always use OpenAI's envelope, so standard SDK error handling works:

```json
{
  "error": {
    "message": "You must provide an 'input' parameter with the text to synthesize.",
    "type": "invalid_request_error",
    "param": "input",
    "code": "missing_input"
  }
}
```

| Status | `code` | When |
| --- | --- | --- |
| 400 | `missing_input` | `input` is missing or empty |
| 400 | `input_too_long` | Text exceeds the configured `max_input_chars` |
| 400 | `invalid_request` | Malformed JSON / body validation failure |
| 400 | `model_not_configured` | No TTS model saved yet — configure one on the API page |
| 400 | `voice_not_configured` | No voice saved yet — configure one on the API page |
| 400 | `model_not_ready` | Configured engine is not installed (install it on the Models page) |
| 400 | `voice_not_found` | Configured voice is unavailable (e.g. Piper voice deleted) |
| 400 | `format_unavailable` | Unknown format, or ffmpeg missing for mp3/opus/aac |
| 401 | `invalid_api_key` | Auth mode is *required* and the key is missing/wrong |
| 429 | `rate_limit_exceeded` | Per-key sliding-window limit hit (retry after N seconds) |
| 503 | `model_loading` | Engine is still loading — the load continues in the background; retry in a few seconds |
| 503 | `engine_busy` | Engine is busy with another request — retry |
| 500 | `internal_error` | Unexpected synthesis failure |

Error `type` is `invalid_request_error` for 400/401, `rate_limit_error` for
429 and `server_error` for 5xx. FastAPI's default 422 validation shape is
translated to this envelope for all `/v1` routes.

### Cold starts & auto-loading

You never have to pre-load the configured engine. The first request after a
server restart triggers a background engine load; the request waits up to 90
seconds for it. If loading takes longer, the API answers `503 model_loading`
and the load keeps running — just retry. Saving the configuration warms the
engine up immediately, so real clients normally never see a cold start.

### Rate limits

Rate limits are **per API key** with a 60-second sliding window, configured
as `rate_limit_per_min` when you create or edit a key (unlimited by default).
Exceeding it returns `429 rate_limit_exceeded` with a retry-after hint.
Anonymous requests in open mode are not rate-limited.

### Code examples

#### cURL — the whole API in one line

```bash
curl http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Today is a wonderful day!"}' \
  --output speech.mp3
```

Ask for a specific format, or send a key when "require API key" is on:

```bash
curl http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-tts-your-key-here" \
  -d '{"input": "Today is a wonderful day!", "output": "wav"}' \
  --output speech.wav
```

#### Python — requests

```python
import requests

resp = requests.post(
    "http://localhost:8000/v1/audio/speech",
    json={"input": "Today is a wonderful day!", "output": "mp3"},
    # headers={"Authorization": "Bearer sk-tts-..."},  # only if keys are required
)
resp.raise_for_status()
with open("speech.mp3", "wb") as f:
    f.write(resp.content)
```

#### Python — official OpenAI SDK

Drop-in compatible: point `base_url` at TTS Studio. SDKs require an API key
and a model name — send placeholders; the server ignores them.

```python
from openai import OpenAI
from pathlib import Path

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

with client.audio.speech.with_streaming_response.create(
    model="tts-1",               # ignored by TTS Studio
    voice="alloy",               # ignored — server voice wins
    input="Today is a wonderful day!",
    response_format="mp3",
) as response:
    response.stream_to_file("speech.mp3")
```

#### JavaScript / TypeScript

```ts
const resp = await fetch("http://localhost:8000/v1/audio/speech", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ input: "Today is a wonderful day!", output: "mp3" }),
});
if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);

const blob = await resp.blob();           // e.g. plug into an <audio> element
document.querySelector("audio").src = URL.createObjectURL(blob);
```

Or with the official `openai` npm package:

```ts
import OpenAI from "openai";
import fs from "fs";

const client = new OpenAI({ baseURL: "http://localhost:8000/v1", apiKey: "not-needed" });
const mp3 = await client.audio.speech.create({
  model: "tts-1",                 // ignored
  voice: "alloy",                 // ignored
  input: "Today is a wonderful day!",
  response_format: "mp3",
});
fs.writeFileSync("speech.mp3", Buffer.from(await mp3.arrayBuffer()));
```

#### Other OpenAI-compatible apps (SillyTavern, LibreChat, …)

Any app that lets you set a custom OpenAI-compatible endpoint works:

| Setting | Value |
| --- | --- |
| Base URL / API URL | `http://<your-server>:8000/v1` (TTS: append `/audio/speech` if the app asks for the full URL) |
| API key | your `sk-tts-…` key — or any placeholder (e.g. `not-needed`) while in open mode |
| Model | any (e.g. `tts-1`) — ignored |
| Voice | any — the server-configured voice is used |

### `GET /v1` — service info

A tiny health/info endpoint so clients can verify the base URL:

```json
{
  "status": "ok",
  "service": "TTS Studio",
  "auth_required": false,
  "endpoints": { "speech": "POST /v1/audio/speech" }
}
```

### Server-side configuration (the API page)

All of the above is configured once in the web UI on the **API** page — no
config files to hand-edit:

1. **TTS model** — a dropdown listing **only installed engines** (uninstalled
   ones are shown disabled with an "install required" hint; install them on
   the Models & Config page first).
2. **Voice** — the chosen engine's voices; for **Piper only downloaded
   voices** are listed, with a hint linking to the catalogue when none are
   downloaded yet.
3. **Defaults** — speaking speed (0.25 – 4.0), default output format, and the
   maximum input length in characters (default 4096).
4. **Save** persists everything to `backend/data/api_config.json` and warms
   the engine up in the background.
5. **API keys** — create, name, rate-limit, revoke and delete keys, with
   per-key usage counters, plus the **"Require an API key"** toggle.

The same operations are available as a local admin API (this is the studio's
own `/api` surface — it is never exposed through the public `/v1` prefix):

| Endpoint | Description |
| --- | --- |
| `GET /api/openai/status` | Public-API status: auth mode, active engine/voice, key counts, ffmpeg availability, supported formats |
| `GET /api/openai/config` | Active configuration + per-engine install/loaded state + available formats |
| `PUT /api/openai/config` | Save the configuration; validates that the engine is installed and the voice available, then triggers a background warm-up |
| `PATCH /api/openai/config/auth` | Toggle `require_api_key` without touching anything else |
| `GET /api/openai/keys` | List keys with usage stats |
| `POST /api/openai/keys` | Create a key (`{"name": "...", "rate_limit_per_min": 60}`) |
| `PATCH /api/openai/keys/{id}` | Rename / change rate limit / revoke |
| `DELETE /api/openai/keys/{id}` | Delete a key permanently |

Saved configuration shape (`PUT /api/openai/config` body):

| Field | Default | Constraints |
| --- | --- | --- |
| `engine` | — (required) | must be an **installed** engine |
| `variant` | `null` | engine-specific flavour (e.g. `piper`, `kokoro-82m`) |
| `voice` | — (required) | must be available for the engine (Piper: downloaded ONNX voices only) |
| `speed` | `1.0` | 0.25 – 4.0 |
| `response_format` | `mp3` | one of the six formats |
| `require_api_key` | `false` | open mode when `false` |
| `max_input_chars` | `4096` | 1 – 100000 |

### Storage & compatibility

- `backend/data/api_config.json` — the single active configuration.
- `backend/data/api_keys.json` — API keys with usage stats (stored in plain
  text by design: this is a local-first, single-user app).
- `backend/data/api_audio/` — temporary render files, deleted right after
  each response is streamed.
- **Upgrading from the old mapping-based API?** `api_config.json` files with
  the legacy `mappings` schema are migrated automatically: the first enabled
  mapping becomes the active engine/voice, and the old defaults carry over.
- CORS is open by default (`TTS_CORS_ORIGINS=*`, see `backend/README.md`),
  so browser-based clients can call the endpoint directly.

---

## Project layout

```
backend/    FastAPI app, engine adapters, job manager, log bus
  app/engines/   kokoro / kitten / pocket / piper adapters + catalogs
  app/routers/   system, models, voices, generate + OpenAI-compatible endpoints
frontend/   React 19 + Vite single-page app
  src/pages/     Studio, Models & Config, API, Logs
  src/components/voice picker, modals, toasts, primitives
```

Runtime data (models, voices, audio, logs) lives in `backend/data/` — see
`backend/README.md` for the backend API overview and configuration variables.

## Notes

- Voices and weights belong to their upstream projects; licences vary per
  model (Kokoro: Apache-2.0, KittenTTS code: Apache-2.0, Pocket TTS:
  CC-BY-4.0, Piper voices: per-voice). Check the upstream model cards before
  commercial use.
- Everything is stored and computed locally; the only network calls are model
  and voice downloads from Hugging Face.
- The speech API is open by default. If you expose it beyond localhost, turn
  on "Require an API key" on the API page (and/or put it behind your proxy's
  auth) so only intended callers can generate audio.
