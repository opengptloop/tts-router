#!/usr/bin/env python3
"""Start the TTS Studio backend.

Usage:
    python run.py [--host 0.0.0.0] [--port 8000] [--reload]
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="TTS Studio backend")
    parser.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default 8000)")
    parser.add_argument("--reload", action="store_true", help="Dev auto-reload")
    args = parser.parse_args()

    from app import config

    uvicorn.run(
        "app.main:app",
        host=args.host or config.HOST,
        port=args.port or config.PORT,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
