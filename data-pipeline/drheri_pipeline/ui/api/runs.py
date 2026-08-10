"""수집 실행(경량) · SSE. Dagster 대신 runner_exec 로 컨테이너 엔진을 async 실행한다."""
from __future__ import annotations

import asyncio

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.ui import engine, runner_exec
from drheri_pipeline.ui.envelope import ApiError, ok, read_json
from drheri_pipeline.ui.events import broadcaster


async def collect(request: Request):
    doc_id = request.path_params["doc_id"]
    body = await read_json(request, require_dict=False)

    if await run_in_threadpool(engine.status) != "ready":
        raise ApiError("engine_not_ready", "엔진을 먼저 켜고 준비될 때까지 기다리세요", status=409)

    def _prepare():
        with conn.session() as cx:
            d = queries.document_detail(cx, doc_id)
            if d is None:
                return None
            conf = float(body.get("conf", d["default_conf"]))
            dpi = int(body.get("dpi", d["default_dpi"]))
            pages = body.get("pages", d["default_pages"]) or ""
            run_id = writes.create_run(cx, doc_id, conf, dpi, pages)
            return d, conf, dpi, pages, run_id

    prepared = await run_in_threadpool(_prepare)
    if prepared is None:
        raise ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    d, conf, dpi, pages, run_id = prepared

    # GPU 공유라 한 번에 1런 — run_engine 내부 전역 락이 큐잉한다. 여기선 즉시 반환.
    asyncio.create_task(runner_exec.run_engine(
        doc_id, run_id, d["url"], d["brand_raw"] or d["brand"], pages, dpi, conf))
    return ok({"ui_run_id": run_id})


async def latest_run(request: Request):
    def _get():
        with conn.session() as cx:
            row = cx.execute(
                "SELECT * FROM run WHERE document_id=? ORDER BY started_at DESC LIMIT 1",
                (request.path_params["doc_id"],)).fetchone()
            return dict(row) if row else None
    run = await run_in_threadpool(_get)
    if run is None:
        raise ApiError("not_found", "수집 이력이 없습니다", status=404)
    return ok(run)


async def events(request: Request):
    q = broadcaster.subscribe()
    return StreamingResponse(broadcaster.sse_stream(q), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


routes = [
    Route("/api/sources/{doc_id:int}/collect", collect, methods=["POST"]),
    Route("/api/sources/{doc_id:int}/runs/latest", latest_run, methods=["GET"]),
    Route("/api/events", events, methods=["GET"]),
]
