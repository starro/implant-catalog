"""운영 API — 검수 동기화, 내보내기, 현황, 설정, 헬스체크, FiftyOne 재기동.

설정은 프로세스 환경변수에 얹는 얇은 계층이다. 값은 data/settings.json 에 저장하고
기동 시 환경변수로 로드한다(별도 설정 서버를 두지 않는다).
"""
from __future__ import annotations

import json
import os

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from drheri_pipeline import storage
from drheri_pipeline.db import conn, queries
from drheri_pipeline.services import export, fiftyone_ctl, sync
from drheri_pipeline.ui.envelope import ApiError, ok, read_json
from drheri_pipeline.ui.events import broadcaster

SETTINGS_KEYS = ("DEFAULT_CONF", "DEFAULT_DPI", "DATA_ROOT", "DAGSTER_URL",
                 "FIFTYONE_URL", "FIFTYONE_SERVICE")
DEFAULTS = {"DEFAULT_CONF": "0.35", "DEFAULT_DPI": "200",
            "DAGSTER_URL": "http://58.229.105.3:3333",
            "FIFTYONE_URL": "http://58.229.105.3:5151",
            "FIFTYONE_SERVICE": "drheri-fiftyone"}

_sync_running = False


def _settings_path():
    return storage.DATA_ROOT / "settings.json"


def _read_settings() -> dict:
    stored = {}
    p = _settings_path()
    if p.exists():
        stored = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for k in SETTINGS_KEYS:
        out[k] = stored.get(k) or os.getenv(k) or DEFAULTS.get(k, "")
    out["DATA_ROOT"] = str(storage.DATA_ROOT)
    return out


async def get_settings(request: Request):
    return ok(await run_in_threadpool(_read_settings))


async def post_settings(request: Request):
    body = await read_json(request)

    def _write():
        cur = _read_settings()
        cur.update({k: str(v) for k, v in body.items() if k in SETTINGS_KEYS})
        cur.pop("DATA_ROOT", None)                # 경로는 환경변수로만 바꾼다
        _settings_path().write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        for k, v in cur.items():
            os.environ[k] = v
        return _read_settings()

    return ok(await run_in_threadpool(_write))


async def post_sync(request: Request):
    global _sync_running
    if _sync_running:
        raise ApiError("sync_in_progress", "검수결과 반영이 이미 진행 중입니다", status=409)
    _sync_running = True
    try:
        result = await run_in_threadpool(sync.run_sync)
    finally:
        _sync_running = False
    broadcaster.publish("sync.finished", result)
    return ok(result)


async def get_overview(request: Request):
    def _load():
        with conn.session() as cx:
            data = queries.overview(cx)
        data["services"] = {"fiftyone": fiftyone_ctl.health()}
        return data

    return ok(await run_in_threadpool(_load))


async def post_export(request: Request):
    result = await run_in_threadpool(export.export_all)
    broadcaster.publish("export.finished", result)
    return ok(result)


async def get_export_summary(request: Request):
    def _load():
        with conn.session() as cx:
            return export.class_distribution(cx)

    return ok(await run_in_threadpool(_load))


async def post_restart(request: Request):
    return ok(await run_in_threadpool(fiftyone_ctl.restart))


async def get_health(request: Request):
    def _check():
        try:
            with conn.session() as cx:
                cx.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    return ok({"db": await run_in_threadpool(_check), "sync_running": _sync_running})


routes = [
    Route("/api/sync", post_sync, methods=["POST"]),
    Route("/api/overview", get_overview, methods=["GET"]),
    Route("/api/export", post_export, methods=["POST"]),
    Route("/api/export/summary", get_export_summary, methods=["GET"]),
    Route("/api/settings", get_settings, methods=["GET"]),
    Route("/api/settings", post_settings, methods=["POST"]),
    Route("/api/fiftyone/restart", post_restart, methods=["POST"]),
    Route("/api/health", get_health, methods=["GET"]),
]
