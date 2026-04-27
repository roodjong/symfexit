#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv run --group docs sphinx-autobuild docs docs/_build/html --open-browser --port 8800 "$@"
