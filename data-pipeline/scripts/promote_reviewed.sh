#!/usr/bin/env bash
# App에서 series 필드를 직접 편집한 review 샘플을 training 으로 승급. 비대화식(REPL X).
set -euo pipefail
cd "$(dirname "$0")/.."

export DATA_ROOT="${DATA_ROOT:-$(pwd)/data}"
export PYTHONPATH="$(pwd)"
export PYTHONIOENCODING=utf-8

PY=".venv/Scripts/python.exe"
[ -f "$PY" ] || PY="c:/dev/image-origin-poc/.venv/Scripts/python.exe"

exec "$PY" scripts/promote_reviewed.py
