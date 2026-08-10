#!/usr/bin/env bash
# 개발서버 서비스 종료 — 관리 UI(uvicorn) + FiftyOne + fiftyone 내장 mongo (시스템 mongo 27017 은 안 건드림)
pkill -f "uvicorn drheri_pipeline.ui.app" 2>/dev/null && echo "관리 UI 종료" || echo "관리 UI 없음"
pkill -f "fo.launch_app"                  2>/dev/null && echo "FiftyOne 종료" || echo "FiftyOne 없음"
pkill -f "fiftyone/db/bin/mongod"         2>/dev/null && echo "fiftyone mongo 종료" || true
echo "완료"
