#!/usr/bin/env bash
# FiftyOne 검수 앱 실행 (포트 5151) — brand×stage saved view 생성 후 App
set -euo pipefail
cd "$(dirname "$0")/.."

export DATA_ROOT="${DATA_ROOT:-$(pwd)/data}"
export PYTHONPATH="$(pwd)"
export PYTHONIOENCODING=utf-8

# venv: 새 레포 .venv 우선, 없으면 image-origin-poc venv 재사용
PY=".venv/Scripts/python.exe"
[ -f "$PY" ] || PY=".venv/bin/python"
[ -f "$PY" ] || PY="c:/dev/image-origin-poc/.venv/Scripts/python.exe"

echo "DATA_ROOT=$DATA_ROOT"
echo "App → http://localhost:5151  (view 드롭다운: <brand>-review / <brand>-training)"
# 인자로 saved view 명을 주면 그 view 에 고정: bash scripts/review.sh GS-review
exec "$PY" scripts/fiftyone_review.py "$@"
