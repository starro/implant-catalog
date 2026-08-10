"""엔진 전원 제어 API."""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from drheri_pipeline.ui import engine
from drheri_pipeline.ui.envelope import ok


async def engine_status(request: Request):
    return ok({"status": await run_in_threadpool(engine.status)})


async def engine_up(request: Request):
    await run_in_threadpool(engine.up)
    return ok({"status": await run_in_threadpool(engine.status)})


async def engine_down(request: Request):
    await run_in_threadpool(engine.down)
    return ok({"status": "down"})


routes = [
    Route("/api/engine/status", engine_status, methods=["GET"]),
    Route("/api/engine/up", engine_up, methods=["POST"]),
    Route("/api/engine/down", engine_down, methods=["POST"]),
]
