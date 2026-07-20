#!/usr/bin/env bash
# 개발서버 서비스 종료 — Dagster + FiftyOne + fiftyone 내장 mongo (시스템 mongo 27017 은 안 건드림)
pkill -f "dagster dev -m drheri_pipeline" 2>/dev/null && echo "Dagster 종료" || echo "Dagster 없음"
pkill -f "fo.launch_app"                  2>/dev/null && echo "FiftyOne 종료" || echo "FiftyOne 없음"
pkill -f "fiftyone/db/bin/mongod"         2>/dev/null && echo "fiftyone mongo 종료" || true
echo "완료"
