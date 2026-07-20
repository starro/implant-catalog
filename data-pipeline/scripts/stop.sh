#!/usr/bin/env bash
# 파이프라인 서버 종료 (FiftyOne ↔ Dagster 정확히 분리, 좀비 세션까지 정리).
#   bash scripts/stop.sh              # 둘 다
#   bash scripts/stop.sh fiftyone     # (=5151) FiftyOne 만 (세션 트리 전체: 서버·워커·mongod). Dagster 안 건드림
#   bash scripts/stop.sh dagster      # (=3333) Dagster 만
#   bash scripts/stop.sh all          # ⚠️ 모든 python + mongod (최후수단)
#
# 핵심: FiftyOne 앱은 세션 python(fiftyone_review/region_split) 1개의 자식으로
#       서버·워커·mongod 까지 ~8개가 매달림 → 세션 python 을 cmdline 으로 찾아
#       'taskkill /T'(트리) 로 죽이면 전부 정리됨 (포트만 죽이면 세션 python 이 좀비로 남음).
set -uo pipefail

# cmdline 정규식에 매칭되는 python 을 '트리째' 종료 (자식 서버/워커/mongod 포함)
kill_py_tree() {
  local pids
  pids=$(powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match '$1' } | ForEach-Object { \$_.ProcessId }" 2>/dev/null | tr -d '\r')
  for pid in $pids; do
    [ -n "$pid" ] && MSYS_NO_PATHCONV=1 taskkill /PID "$pid" /T /F >/dev/null 2>&1 || true
  done
}
kill_mongod() { MSYS_NO_PATHCONV=1 taskkill /IM mongod.exe /F >/dev/null 2>&1 || true; }

stop_fiftyone() {
  echo "FiftyOne 종료 (세션 트리 전체 + mongod)"
  kill_py_tree 'region_split|fiftyone_review|fiftyone'   # 세션 python + 자식(서버/워커) + 고아 fiftyone 서비스
  kill_mongod                                            # 떨어져나온 mongod 보강
}
stop_dagster() {
  echo "Dagster 종료 (dagster 세션 트리)"
  kill_py_tree 'dagster'                                 # dagster dev + webserver + daemon + code-server
}

case "${1:-both}" in
  all)
    echo "⚠️ 모든 python + mongod 종료 (Dagster 포함)"
    MSYS_NO_PATHCONV=1 taskkill /IM python.exe /F >/dev/null 2>&1 || true
    kill_mongod ;;
  fiftyone|5151) stop_fiftyone ;;
  dagster|3333)  stop_dagster ;;
  both|"")       stop_fiftyone; stop_dagster ;;
  *) echo "usage: stop.sh [fiftyone|dagster|all]"; exit 1 ;;
esac
echo "완료. (남은 python: $(tasklist 2>/dev/null | grep -ic python.exe))"
