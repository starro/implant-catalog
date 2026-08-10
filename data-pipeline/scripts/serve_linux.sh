#!/usr/bin/env bash
# 개발서버(CentOS8, sudo 없음)용 — 관리 UI(uvicorn) + FiftyOne(:5151) nohup 기동.
# FiftyOne mongo = 교체된 MongoDB 4.4(AVX 불필요), 검증 끔(min 6.0 우회).
# 접속: 로컬에서  ssh -L 8090:localhost:8090 -L 5151:localhost:5151 jay8126@<host>
set -e
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$PWD"
export DATA_ROOT="${DATA_ROOT:-$PWD/data}"
export HF_HOME="${HF_HOME:-$PWD/hf_cache}"
export FIFTYONE_DATABASE_VALIDATION=false     # CPU AVX 없어 mongo4.4 사용 → fiftyone min(6.0) 검증 끔
mkdir -p "$DATA_ROOT"
PY="$PWD/.venv/bin/python"
# 바인딩 주소: 기본 0.0.0.0(사내망에서 IP 로 직접 접속). localhost 전용으로 하려면 BIND=127.0.0.1
BIND="${BIND:-0.0.0.0}"
# 포트: 이 서버 방화벽이 3000/5000/8090 만 열려 있어 그 중에서 사용 (5151 은 차단됨)
UI_PORT="${UI_PORT:-8090}"
FIFTYONE_PORT="${FIFTYONE_PORT:-5000}"

nohup "$PY" -m uvicorn drheri_pipeline.ui.app:app --host "$BIND" --port "$UI_PORT" > "$HOME/ui.log" 2>&1 &
echo "관리 UI  :$UI_PORT  pid $!  (bind $BIND)"
nohup "$PY" -c "
import sys; sys.path.insert(0, 'scripts')
import fiftyone as fo, fiftyone_review as R
ds = R.build_dataset(); R.build_views(ds)       # manifest 에서 drheri 빌드 (로컬 review.sh 와 동일)
print('drheri', ds.count(), 'samples')
s = fo.launch_app(ds, remote=True, port=$FIFTYONE_PORT, address='$BIND'); s.wait(-1)
" > "$HOME/fiftyone.log" 2>&1 &
echo "FiftyOne :$FIFTYONE_PORT  pid $!  (bind $BIND, drheri 빌드 후 서빙)"
echo "로그: ~/ui.log  ~/fiftyone.log"
