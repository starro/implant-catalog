#!/usr/bin/env bash
# 대화형 라벨링 세션 (FiftyOne App + Python 프롬프트). 본인 터미널에서 실행.
# App 에서 샘플 선택 후 프롬프트:  label(series='SS2')  →  keep()  →  promote_keeps()
set -euo pipefail
cd "$(dirname "$0")/.."

export DATA_ROOT="${DATA_ROOT:-$(pwd)/data}"
export PYTHONPATH="$(pwd)"
export PYTHONIOENCODING=utf-8
export HF_HOME="${HF_HOME:-c:/dev/image-origin-poc/hf_cache}"

PY=".venv/Scripts/python.exe"
[ -f "$PY" ] || PY="c:/dev/image-origin-poc/.venv/Scripts/python.exe"

echo "라벨링 세션 시작 — App http://localhost:5151"
exec "$PY" -i scripts/label_session.py
