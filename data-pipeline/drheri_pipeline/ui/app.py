"""Dr.HERi 데이터 파이프라인 관리 UI — JSON API + 정적 SPA 서빙.

실행: uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000
"""
from __future__ import annotations

from starlette.applications import Starlette

from drheri_pipeline.db import conn
from drheri_pipeline.ui.api import ops, runs, sources
from drheri_pipeline.ui.envelope import ApiError, api_error_handler, unhandled_error_handler


def create_app() -> Starlette:
    conn.migrate()
    return Starlette(
        routes=[*sources.routes, *runs.routes, *ops.routes],
        exception_handlers={ApiError: api_error_handler, Exception: unhandled_error_handler},
    )


app = create_app()
