"""카탈로그 PDF 업로드 — data/catalog/<브랜드>/<이름>-<sha8>.pdf 로 저장.

NAS 가 개발서버에서 도달 불가하여, 사용자가 브라우저로 PDF 를 올린다.
저장 경로(서버 절대경로)를 반환하면 모달이 그걸 등록 폼의 주소 칸에 채운다.
등록·수집 로직은 이 경로를 기존 url 필드로 그대로 흘려보낸다(변경 없음).
"""
from __future__ import annotations

from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from drheri_pipeline import storage
from drheri_pipeline.normalize import safe_component
from drheri_pipeline.taxonomy import normalize_brand
from drheri_pipeline.ui.envelope import ApiError, ok

MAX_BYTES = 100 * 1024 * 1024        # 100MB


def _store(data: bytes, filename: str, brand_raw: str) -> dict:
    """검증된 PDF 를 data/catalog/<정규화 브랜드>/<이름>-<sha8>.pdf 에 저장.

    같은 내용이면 <이름>-<sha8> 이 같아 동일 경로가 된다(멱등). 이미 있으면 다시 쓰지 않는다.
    """
    brand = normalize_brand(brand_raw) or "_unknown"
    stem = safe_component(Path(filename).stem)
    sha8 = storage.content_hash(data)[:8]
    dst = storage.DATA_ROOT / "catalog" / safe_component(brand) / f"{stem}-{sha8}.pdf"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        dst.write_bytes(data)
    return {"path": str(dst.resolve()), "filename": filename, "brand": brand}


async def upload(request: Request):
    form = await request.form()
    brand_raw = (form.get("brand") or "").strip()
    if not brand_raw:
        raise ApiError("invalid_request", "브랜드를 먼저 입력하세요")

    upload_file = form.get("file")
    filename = getattr(upload_file, "filename", None)
    if upload_file is None or not filename:
        raise ApiError("invalid_request", "파일이 없습니다")

    content_type = (getattr(upload_file, "content_type", "") or "").lower()
    if not filename.lower().endswith(".pdf") or content_type != "application/pdf":
        raise ApiError("invalid_file", "PDF 파일만 업로드할 수 있습니다")

    data = await upload_file.read()
    if len(data) > MAX_BYTES:
        raise ApiError("file_too_large", "파일이 너무 큽니다 (최대 100MB)")

    result = await run_in_threadpool(_store, data, filename, brand_raw)
    return ok(result)


routes = [
    Route("/api/uploads", upload, methods=["POST"]),
]
