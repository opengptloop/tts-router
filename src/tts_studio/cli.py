"""``tts-studio`` command line interface.

Starts the whole application in a single process:

* The FastAPI backend serves the built web UI, the studio API and the
  OpenAI-compatible ``/v1`` API - all on ONE local port.
* Your browser opens the app automatically.
* There is no separate backend port to remember or expose: the single URL
  printed in the terminal IS the application.

Runtime data (models, voices, audio, config) lives in ``~/.tts-studio`` by
default; override with ``--data-dir`` or the ``TTS_DATA_DIR`` environment
variable.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _free_port(host: str, preferred: int) -> int:
    """Return ``preferred`` if it is available, else the next free port."""
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(
        f"error: no free port found between {preferred} and {preferred + 49}"
    )


def _open_browser_when_ready(url: str, host: str, port: int) -> None:
    """Wait until the server accepts connections, then open the browser."""

    def _wait_and_open() -> None:
        deadline = time.time() + 30
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                try:
                    sock.connect((host, port))
                except OSError:
                    time.sleep(0.25)
                    continue
                break
        webbrowser.open(url)

    threading.Thread(target=_wait_and_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tts-studio",
        description=(
            "Launch the TTS Studio web app - local-first text-to-speech with "
            "Kokoro, Kitten, Pocket and Piper. One command, one port, no API keys."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind address (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to serve on (default: {DEFAULT_PORT}; auto-skips busy ports)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directory for models, voices and audio (default: ~/.tts-studio)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser automatically",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__import__('tts_studio').__version__}",
    )
    args = parser.parse_args(argv)

    # --- Configure the runtime environment BEFORE importing the app. -------
    # tts_studio.config reads these at import time.
    if args.data_dir:
        os.environ["TTS_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    os.environ.setdefault("TTS_HOST", args.host)

    from tts_studio import __version__

    port = _free_port(args.host, args.port if args.port is not None else DEFAULT_PORT)
    display_host = "localhost" if args.host in ("0.0.0.0", "::", "") else args.host
    url = f"http://{display_host}:{port}"
    data_dir = os.environ.get("TTS_DATA_DIR", "~/.tts-studio")

    print()
    print(f"  TTS Studio v{__version__}")
    print(f"  {'-' * 46}")
    print(f"  App      : {url}")
    print(f"  Data dir : {data_dir}")
    print(f"  Stop     : Ctrl+C")
    print()
    print("  The UI, the studio API and the OpenAI-compatible /v1 API are all")
    print("  served from the single URL above - no backend port to manage.")
    print()

    if not args.no_browser:
        _open_browser_when_ready(url, args.host, port)

    try:
        import uvicorn

        uvicorn.run(
            "tts_studio.main:app",
            host=args.host,
            port=port,
            log_level="warning",
            # The app prints its own banner; uvicorn stays quiet.
        )
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
