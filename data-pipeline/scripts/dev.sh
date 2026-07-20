#!/usr/bin/env bash
# Dagster UI (포트 3333) — DATA_ROOT/DAGSTER_HOME 자동 설정
set -euo pipefail
cd "$(dirname "$0")/.."

export DATA_ROOT="${DATA_ROOT:-$(pwd)/data}"
export DAGSTER_HOME="${DAGSTER_HOME:-$(pwd)/.dagster_home}"
export HF_HOME="${HF_HOME:-c:/dev/image-origin-poc/hf_cache}"   # DocLayout 모델 캐시
mkdir -p "$DATA_ROOT" "$DAGSTER_HOME"

VENV_PY=".venv/Scripts/python.exe"
[ -f "$VENV_PY" ] || VENV_PY=".venv/bin/python"
[ -f "$VENV_PY" ] || VENV_PY="c:/dev/image-origin-poc/.venv/Scripts/python.exe"   # 새 레포 venv 없으면 PoC venv 재사용

echo "DATA_ROOT=$DATA_ROOT"
echo "DAGSTER_HOME=$DAGSTER_HOME"
exec "$VENV_PY" -m dagster dev -m drheri_pipeline.definitions --port 3333
