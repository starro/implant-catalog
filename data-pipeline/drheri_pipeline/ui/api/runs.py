"""수집 실행 · 완료 훅 · SSE.

완료 감지는 Dagster run_status_sensor 가 /api/hooks/run-finished 를 때리는 푸시 방식이다.
훅을 놓친 경우(UI 재시작 등)에 대비해 /runs/latest 가 1회 정정한다 — 상시 폴링이 아니다.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.services import fiftyone_ctl
from drheri_pipeline.ui import dagster_client
from drheri_pipeline.ui.envelope import ApiError, ok, read_json
from drheri_pipeline.ui.events import broadcaster

HOOK_TOKEN = os.getenv("HOOK_TOKEN", "drheri-dev")
DAGSTER_TERMINAL = {"SUCCESS", "FAILURE", "CANCELED"}
STALL_LIMIT = timedelta(minutes=30)


async def collect(request: Request):
    doc_id = request.path_params["doc_id"]
    body = await read_json(request, require_dict=False)

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

    try:
        dagster_run_id = await run_in_threadpool(
            lambda: dagster_client.submit(
                pdf_url=d["url"], brand=d["brand_raw"] or d["brand"],
                series=d["default_series"], conf=conf, dpi=dpi, pages=pages,
                document_id=doc_id, ui_run_id=run_id))
    except Exception as e:  # noqa: BLE001
        def _fail():
            with conn.session() as cx:
                writes.finish_run(cx, run_id, "FAILURE", 0, f"{e.__class__.__name__}: {e}")
        await run_in_threadpool(_fail)
        raise ApiError("dagster_submit_failed", f"수집 실행에 실패했습니다: {e}", status=502)

    def _attach():
        with conn.session() as cx:
            writes.attach_dagster_run(cx, run_id, dagster_run_id)

    await run_in_threadpool(_attach)
    return ok({"ui_run_id": run_id, "dagster_run_id": dagster_run_id})


def _stalled(started_at: str) -> bool:
    """훅도 못 받고 Dagster 도 종료를 알리지 않은 채 STALL_LIMIT 을 넘겼는지."""
    try:
        started = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return False
    return datetime.now(timezone.utc) - started > STALL_LIMIT


def _reconcile_latest(doc_id: int) -> dict | None:
    """최신 런 1건 조회. 진행 중이면 Dagster 에 한 번 물어 정정한다(상시 폴링 아님)."""
    with conn.session() as cx:
        row = cx.execute(
            """SELECT * FROM run WHERE document_id=? ORDER BY started_at DESC LIMIT 1""",
            (doc_id,)).fetchone()
        if row is None:
            return None
        run = dict(row)

    if run["status"] not in ("QUEUED", "RUNNING"):
        return run

    st = dagster_client.status(run["dagster_run_id"]) if run["dagster_run_id"] else None
    if st in DAGSTER_TERMINAL:
        final = st
    elif _stalled(run["started_at"]):
        final = "TIMEOUT"                       # 스펙 §13 — 30분 이상 멈춰 있으면 시간초과
    else:
        return run

    with conn.session() as cx:
        writes.finish_run(cx, run["id"], final, run["extracted"], run["error"])
    run["status"] = final
    return run


async def latest_run(request: Request):
    run = await run_in_threadpool(_reconcile_latest, request.path_params["doc_id"])
    if run is None:
        raise ApiError("not_found", "수집 이력이 없습니다", status=404)
    return ok(run)


async def run_log(request: Request):
    run_id = request.path_params["run_id"]

    def _get():
        with conn.session() as cx:
            row = cx.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    run = await run_in_threadpool(_get)
    if run is None:
        raise ApiError("not_found", "런을 찾을 수 없습니다", status=404)
    base = os.getenv("DAGSTER_URL", "http://58.229.105.3:3333")
    url = f"{base}/runs/{run['dagster_run_id']}" if run["dagster_run_id"] else None
    return ok({"run": run, "dagster_url": url})


def _sync_saved_views_safely() -> dict:
    """FiftyOne saved view 자동 갱신. 실패해도 훅 처리 자체는 실패시키지 않는다(FiftyOne 미설치 포함)."""
    from scripts.fiftyone_saved_views import sync_views_safely
    return sync_views_safely()


async def hook_run_finished(request: Request):
    if request.headers.get("X-Hook-Token") != HOOK_TOKEN:
        raise ApiError("unauthorized", "훅 토큰이 올바르지 않습니다", status=401)
    body = await read_json(request, require_dict=False)
    ui_run_id = int(body.get("ui_run_id") or 0)
    status = (body.get("status") or "").upper()
    if not ui_run_id or status not in DAGSTER_TERMINAL:
        raise ApiError("invalid_request", "ui_run_id 와 status 가 필요합니다")

    hook_extracted = int(body.get("extracted") or 0)
    error = body.get("error")

    def _finish():
        with conn.session() as cx:
            row = cx.execute("SELECT document_id, extracted FROM run WHERE id=?",
                             (ui_run_id,)).fetchone()
            # 센서는 실제 추출 개수를 모르므로 훅 본문의 extracted 는 항상 0 이다.
            # 그 경우 record_ingest() 가 수집 중에 이미 기록해 둔 run.extracted 값을 덮어쓰지 않는다.
            extracted = hook_extracted if hook_extracted else (row["extracted"] if row else 0)
            writes.finish_run(cx, ui_run_id, status, extracted, error)
            return (row["document_id"] if row else None), extracted

    doc_id, extracted = await run_in_threadpool(_finish)

    restart = None
    saved_views = None
    if status == "SUCCESS":
        restart = await run_in_threadpool(fiftyone_ctl.restart)
        saved_views = await run_in_threadpool(_sync_saved_views_safely)

    broadcaster.publish("run.finished", {
        "ui_run_id": ui_run_id, "document_id": doc_id, "status": status,
        "extracted": extracted, "error": error, "fiftyone": restart,
        "saved_views": saved_views})
    return ok({"ui_run_id": ui_run_id, "fiftyone": restart, "saved_views": saved_views})


async def events(request: Request):
    q = broadcaster.subscribe()
    return StreamingResponse(broadcaster.sse_stream(q), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


routes = [
    Route("/api/sources/{doc_id:int}/collect", collect, methods=["POST"]),
    Route("/api/sources/{doc_id:int}/runs/latest", latest_run, methods=["GET"]),
    Route("/api/runs/{run_id:int}/log", run_log, methods=["GET"]),
    Route("/api/hooks/run-finished", hook_run_finished, methods=["POST"]),
    Route("/api/events", events, methods=["GET"]),
]
