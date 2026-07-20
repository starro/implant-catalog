#!/usr/bin/env bash
# 'accept' 태그된 figure 의 series = suggested_series 로 확정. 비대화식.
set -uo pipefail
cd "$(dirname "$0")/.."
export DATA_ROOT="${DATA_ROOT:-$(pwd)/data}"
export PYTHONPATH="$(pwd)"
export PYTHONIOENCODING=utf-8
PY=".venv/Scripts/python.exe"
[ -f "$PY" ] || PY="c:/dev/image-origin-poc/.venv/Scripts/python.exe"
exec "$PY" scripts/accept_suggested.py
