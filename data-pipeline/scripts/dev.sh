#!/usr/bin/env bash
# 관리 UI(uvicorn, 포트 3000) — DATA_ROOT 자동 설정
set -euo pipefail
cd "$(dirname "$0")/.."

export DATA_ROOT="${DATA_ROOT:-$(pwd)/data}"
export HF_HOME="${HF_HOME:-c:/dev/image-origin-poc/hf_cache}"   # DocLayout 모델 캐시
mkdir -p "$DATA_ROOT"

VENV_PY=".venv/Scripts/python.exe"
[ -f "$VENV_PY" ] || VENV_PY=".venv/bin/python"
[ -f "$VENV_PY" ] || VENV_PY="c:/dev/image-origin-poc/.venv/Scripts/python.exe"   # 새 레포 venv 없으면 PoC venv 재사용

echo "DATA_ROOT=$DATA_ROOT"
exec "$VENV_PY" -m uvicorn drheri_pipeline.ui.app:app --port 3000
