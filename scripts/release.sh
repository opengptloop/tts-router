#!/usr/bin/env bash
# Build and publish TTS Studio to PyPI.
#
# Usage:
#   ./scripts/release.sh              # build + upload the current version
#   ./scripts/release.sh 1.0.1        # bump the version first, then build + upload
#
# Requires:
#   - python3 with the `build` and `twine` packages (installed automatically)
#   - node/npm to rebuild the frontend bundle
#   - PyPI credentials: either a ~/.pypirc or the environment variables
#       TWINE_USERNAME=__token__
#       TWINE_PASSWORD=pypi-<your-api-token>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- optional version bump ---------------------------------------------------
if [[ $# -ge 1 ]]; then
  VERSION="$1"
  sed -i.bak "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml && rm -f pyproject.toml.bak
  sed -i.bak "s/^__version__ = \".*\"/__version__ = \"$VERSION\"/" src/tts_studio/__init__.py && rm -f src/tts_studio/__init__.py.bak
  echo ">> Version bumped to $VERSION"
fi

CURRENT_VERSION="$(
  python3 -c "import re; print(re.search(r'^__version__ = \"(.*)\"', open('src/tts_studio/__init__.py').read()).group(1))"
)"
PYPROJECT_VERSION="$(
  python3 -c "import re; print(re.search(r'^version = \"(.*)\"', open('pyproject.toml').read()).group(1))"
)"
if [[ "$CURRENT_VERSION" != "$PYPROJECT_VERSION" ]]; then
  echo "error: version mismatch: pyproject.toml=$PYPROJECT_VERSION __init__.py=$CURRENT_VERSION" >&2
  exit 1
fi
echo ">> Releasing tts-studio $CURRENT_VERSION"

# --- rebuild the web UI and refresh the bundled copy --------------------------
echo ">> Building frontend..."
(cd frontend && npm install --no-audit --no-fund && npm run build)
rm -rf src/tts_studio/frontend_dist
cp -r frontend/dist src/tts_studio/frontend_dist

# --- build distributions -------------------------------------------------------
echo ">> Installing build tools..."
python3 -m pip install -q build twine
rm -rf dist
echo ">> Building sdist + wheel..."
python3 -m build
echo ">> Built:"
ls -1 dist

# --- upload --------------------------------------------------------------------
echo ">> Uploading to PyPI..."
python3 -m twine upload --non-interactive dist/*

echo
echo ">> Released: https://pypi.org/project/tts-studio/$CURRENT_VERSION/"
