"""Allow ``python -m tts_studio`` to work the same as the ``tts-studio`` command."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
