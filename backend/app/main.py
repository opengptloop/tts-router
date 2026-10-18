"""TTS Studio backend - FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .engines.base import EngineError
from .jobs import JOBS
from .logbus import BUS, configure_logging
from .model_manager import get_manager
from .routers import generate, models, system, voices
from .routers import openai_admin, openai_api

logger = logging.getLogger("tts.main")

STATUS_FOR_CODE = {
    "not_installed": 409,
    "catalog_unavailable": 503,
    "voice_not_downloaded": 409,
    "engine_busy": 409,
    "download_incomplete": 502,
    "install_failed": 502,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    BUS.set_loop(asyncio.get_running_loop())
    BUS.append(
        "INFO",
        "tts.main",
        f"{config.APP_NAME} v{config.APP_VERSION} backend started "
        f"(data dir: {config.DATA_DIR})",
    )
    manager = get_manager()
    installed = [e.name for e in manager.engines.values() if e.installed()]
    missing = [e.name for e in manager.engines.values() if not e.installed()]
    BUS.append("INFO", "tts.main", f"Installed engines: {', '.join(installed) or 'none'}")
    if missing:
        BUS.append(
            "WARNING",
            "tts.main",
            f"Not installed: {', '.join(missing)} (install them from the Models page)",
        )
    yield
    BUS.append("INFO", "tts.main", "Backend shutting down")
    JOBS.shutdown()


app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description=(
        "Local-first text-to-speech studio for Kokoro, Kitten, Pocket and Piper. "
        "All inference happens on this machine."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(EngineError)
async def engine_error_handler(_request: Request, exc: EngineError) -> JSONResponse:
    status = STATUS_FOR_CODE.get(exc.code, 400)
    return JSONResponse(status_code=status, content={"detail": str(exc), "code": exc.code})


app.include_router(system.router)
app.include_router(models.router)
app.include_router(voices.router)
app.include_router(generate.router)
app.include_router(openai_admin.router)
app.include_router(openai_api.router)

# FastAPI's 422 validation shape must not leak onto the OpenAI-compatible
# surface: /v1 clients always get {"error": {...}} bodies (400).
app.add_exception_handler(
    RequestValidationError,
    openai_api.openai_validation_error_handler,
)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = BUS.subscribe()
    try:
        for record in BUS.tail(after_seq=0, limit=200):
            await websocket.send_json(record)
        while True:
            record = await queue.get()
            await websocket.send_json(record)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - client went away
        pass
    finally:
        BUS.unsubscribe(queue)


# ---------------------------------------------------------------------------
# Optional: serve a built frontend (single-service deployment)
# ---------------------------------------------------------------------------

_frontend_dist = config.BASE_DIR.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=_frontend_dist / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):  # pragma: no cover - static serving
        if full_path.startswith(("api/", "ws/")):
            raise EngineError("Not found", code="not_found")
        candidate = _frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_frontend_dist / "index.html")
