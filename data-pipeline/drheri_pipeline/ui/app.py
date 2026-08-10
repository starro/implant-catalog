"""Dr.HERi 데이터 파이프라인 관리 UI — JSON API + 정적 SPA 서빙.

실행: uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000
화면 빌드: cd web && npm run build   (→ web/dist)
"""
from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from drheri_pipeline.db import conn
from drheri_pipeline.ui.api import ops, runs, sources, uploads
from drheri_pipeline.ui.api import engine as engine_api
from drheri_pipeline.ui.envelope import ApiError, api_error_handler, fail, unhandled_error_handler

DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


async def spa(request: Request):
    """SPA 진입점. 라우팅은 해시로 하므로 index.html 하나면 충분하다."""
    index = DIST / "index.html"
    if not index.exists():
        return fail("ui_not_built",
                    "화면이 아직 빌드되지 않았습니다. `cd web && npm run build` 를 실행하세요.",
                    status=503)
    return FileResponse(index)


def create_app() -> Starlette:
    conn.migrate()
    routes = [*sources.routes, *runs.routes, *ops.routes, *uploads.routes, *engine_api.routes]
    if (DIST / "assets").exists():
        routes.append(Mount("/assets", app=StaticFiles(directory=DIST / "assets")))
    routes.append(Route("/", spa, methods=["GET"]))
    return Starlette(
        routes=routes,
        exception_handlers={ApiError: api_error_handler, Exception: unhandled_error_handler},
    )


app = create_app()
