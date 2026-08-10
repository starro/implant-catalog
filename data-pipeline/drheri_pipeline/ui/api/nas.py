"""NAS 파일 브라우저 — 호스트에 마운트된 카탈로그 루트 아래를 샌드박스 탐색.

NAS 는 DGX 호스트에 읽기전용 CIFS 로 마운트된다(/mnt/nas). 여기서 고른 PDF 의
호스트 절대경로를 등록 폼의 url 로 흘려보내면, 수집 시 _prepare_pdf 가 docker cp
로 컨테이너에 주입한다(업로드 흐름과 동일). 별도 컨테이너 변경 없음.
"""
from __future__ import annotations

import os
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from drheri_pipeline.ui.envelope import ApiError, ok

DEFAULT_ROOT = "/mnt/nas/03. Dr.HERi/02. 카탈로그"


def _root() -> Path:
    return Path(os.getenv("NAS_CATALOG_ROOT") or DEFAULT_ROOT)


def _safe_target(root_r: Path, rel: str) -> Path:
    """이미 resolve 된 root 아래로만 해석한다. '..'·절대경로로 탈출하면 403."""
    target = (root_r / rel).resolve()
    if target != root_r and root_r not in target.parents:
        raise ApiError("forbidden", "허용된 경로를 벗어났습니다", status=403)
    return target


def _browse(rel: str) -> dict:
    root = _root()
    root_r = root.resolve() if root.exists() else root
    if not root_r.is_dir():                       # NAS 미마운트 등 — UI 가 안내만 하면 됨
        return {"available": False, "root": str(root), "path": "", "dirs": [], "files": []}
    target = _safe_target(root_r, rel)
    if not target.is_dir():
        raise ApiError("not_found", "폴더를 찾을 수 없습니다", status=404)

    dirs: list[dict] = []
    files: list[dict] = []
    with os.scandir(target) as it:
        for e in it:
            if e.name.startswith("."):
                continue
            rel_path = os.path.relpath(e.path, str(root_r)).replace(os.sep, "/")
            try:
                is_dir = e.is_dir()
            except OSError:
                continue
            if is_dir:
                dirs.append({"name": e.name, "path": rel_path})
            elif e.name.lower().endswith(".pdf"):
                try:
                    size = e.stat().st_size
                except OSError:
                    size = 0
                files.append({"name": e.name,
                              "abs": str(Path(e.path).resolve()), "size": size})
    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    return {"available": True, "root": str(root_r),
            "path": rel.strip("/"), "dirs": dirs, "files": files}


async def browse(request: Request):
    rel = request.query_params.get("path") or ""
    return ok(await run_in_threadpool(_browse, rel))


def _pdf_pages(rel: str) -> dict:
    """선택한 NAS PDF 의 총 페이지 수. 페이지 범위 지정을 돕기 위해 UI 가 보여준다."""
    root = _root()
    root_r = root.resolve() if root.exists() else root
    if not root_r.is_dir():
        raise ApiError("unavailable", "NAS 가 마운트되어 있지 않습니다", status=409)
    target = _safe_target(root_r, rel)
    if not target.is_file() or not target.name.lower().endswith(".pdf"):
        raise ApiError("not_found", "PDF 파일을 찾을 수 없습니다", status=404)
    from pypdf import PdfReader                       # 페이지 수만 — 렌더링 없음
    try:
        pages = len(PdfReader(str(target)).pages)
    except Exception as e:  # noqa: BLE001 — 손상/암호화 PDF 등
        raise ApiError("pdf_error", f"PDF 페이지 수를 읽을 수 없습니다: {e}", status=422) from e
    return {"name": target.name, "pages": pages, "size": target.stat().st_size}


async def pdfinfo(request: Request):
    rel = request.query_params.get("path") or ""
    if not rel:
        raise ApiError("invalid_request", "path 파라미터가 필요합니다")
    return ok(await run_in_threadpool(_pdf_pages, rel))


routes = [
    Route("/api/nas/browse", browse, methods=["GET"]),
    Route("/api/nas/pdfinfo", pdfinfo, methods=["GET"]),
]
