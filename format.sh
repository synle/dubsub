#!/usr/bin/env bash
# Format Python sources with black + ruff (auto-fix).
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v uvx >/dev/null 2>&1; then
  echo "uvx not found. Install uv: brew install uv  (or: pipx install uv)" >&2
  exit 1
fi
uvx black .
uvx ruff check --fix .
