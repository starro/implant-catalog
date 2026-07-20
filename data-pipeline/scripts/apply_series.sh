#!/usr/bin/env bash
# App에서 단 series 태그(SS2/SS3)를 읽어 series 부여 + training 승급. 비대화식(REPL X).
set -euo pipefail
cd "$(dirname "$0")/.."

export DATA_ROOT="${DATA_ROOT:-$(pwd)/data}"
export PYTHONPATH="$(pwd)"
export PYTHONIOENCODING=utf-8

PY=".venv/Scripts/python.exe"
[ -f "$PY" ] || PY="c:/dev/image-origin-poc/.venv/Scripts/python.exe"

exec "$PY" scripts/apply_series.py
