"""소스(브랜드 › 문서) API."""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.services import purge
from drheri_pipeline.ui.envelope import ApiError, ok, read_json

_UPDATE_MAP = {"name": "name", "memo": "memo", "conf": "default_conf",
               "dpi": "default_dpi", "pages": "default_pages", "series": "default_series"}


def _list_tree() -> list[dict]:
    with conn.session() as cx:
        return queries.source_tree(cx)


async def list_sources(request: Request):
    return ok(await run_in_threadpool(_list_tree))


async def check_url(request: Request):
    url = (request.query_params.get("url") or "").strip()
    if not url:
        raise ApiError("invalid_request", "url 파라미터가 필요합니다")

    def _find():
        with conn.session() as cx:
            return queries.find_document_by_url(cx, url)

    doc = await run_in_threadpool(_find)
    return ok({"exists": doc is not None, "document": doc})


async def create_source(request: Request):
    body = await read_json(request)
    url = (body.get("url") or "").strip()
    if not url:
        raise ApiError("invalid_request", "URL 을 입력하세요")
    brand = (body.get("brand") or "").strip()
    if not brand:
        raise ApiError("invalid_request", "브랜드를 입력하세요")
    name = (body.get("name") or "").strip() or url.rsplit("/", 1)[-1] or url

    def _create():
        with conn.session() as cx:
            return writes.create_document(
                cx, brand_raw=brand, name=name, url=url,
                source_type=body.get("source_type") or "catalog_pdf",
                default_conf=float(body.get("conf") or 0.35),
                default_dpi=int(body.get("dpi") or 200),
                default_pages=body.get("pages") or "",
                default_series=body.get("series") or "_unknown",
                memo=body.get("memo") or "")

    try:
        doc_id = await run_in_threadpool(_create)
    except writes.DuplicateUrl as e:
        raise ApiError("duplicate_url", "이미 등록된 URL 입니다", status=409) from e
    return ok({"id": doc_id})


async def get_source(request: Request):
    doc_id = request.path_params["doc_id"]

    def _detail():
        with conn.session() as cx:
            return queries.document_detail(cx, doc_id)

    detail = await run_in_threadpool(_detail)
    if detail is None:
        raise ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    return ok(detail)


async def update_source(request: Request):
    doc_id = request.path_params["doc_id"]
    body = await read_json(request)
    fields = {_UPDATE_MAP[k]: v for k, v in body.items() if k in _UPDATE_MAP}
    if "brand" in body and (body["brand"] or "").strip():
        fields["brand_raw"] = body["brand"].strip()
    if "default_conf" in fields:
        fields["default_conf"] = float(fields["default_conf"])
    if "default_dpi" in fields:
        fields["default_dpi"] = int(fields["default_dpi"])

    def _update():
        with conn.session() as cx:
            if queries.document_detail(cx, doc_id) is None:
                return False
            writes.update_document(cx, doc_id, **fields)
            return True

    if not await run_in_threadpool(_update):
        raise ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    return ok({"id": doc_id})


async def archive_source(request: Request):
    doc_id = request.path_params["doc_id"]

    def _archive():
        with conn.session() as cx:
            writes.archive_document(cx, doc_id)

    await run_in_threadpool(_archive)
    return ok({"id": doc_id})


async def reset_source(request: Request):
    """수집 초기화 — 문서는 유지하고 수집 결과(이미지·런·FiftyOne 샘플·파일)만 지운다."""
    doc_id = request.path_params["doc_id"]
    result = await run_in_threadpool(purge.reset_document, doc_id)
    if result is None:
        raise ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    return ok(result)


routes = [
    Route("/api/sources", list_sources, methods=["GET"]),
    Route("/api/sources/check", check_url, methods=["GET"]),
    Route("/api/sources", create_source, methods=["POST"]),
    Route("/api/sources/{doc_id:int}", get_source, methods=["GET"]),
    Route("/api/sources/{doc_id:int}/update", update_source, methods=["POST"]),
    Route("/api/sources/{doc_id:int}/archive", archive_source, methods=["POST"]),
    Route("/api/sources/{doc_id:int}/reset", reset_source, methods=["POST"]),
]
