"""API 응답 봉투 — 모든 라우트가 {ok, data, error} 로만 응답한다."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse


class ApiError(Exception):
    """라우트에서 던지면 봉투 형태로 변환된다."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


async def read_json(request: Request, *, require_dict: bool = True) -> dict:
    """요청 본문을 JSON dict 로 파싱한다.

    파싱 자체가 실패하면(깨진 JSON) 항상 400 invalid_request 를 던진다.
    require_dict=True(기본) 면 최상위 값이 dict 가 아닐 때도 400 을 던진다.
    require_dict=False 면 dict 가 아닌 경우 빈 dict 를 돌려준다(관대한 파싱이 필요한 훅 등).
    """
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        raise ApiError("invalid_request", "JSON 본문을 해석할 수 없습니다") from e
    if isinstance(body, dict):
        return body
    if require_dict:
        raise ApiError("invalid_request", "JSON 객체가 필요합니다")
    return {}


def ok(data=None, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data, "error": None}, status_code=status)


def fail(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "data": None,
                         "error": {"code": code, "message": message}}, status_code=status)


def api_error_handler(request, exc: ApiError) -> JSONResponse:
    return fail(exc.code, exc.message, exc.status)


def unhandled_error_handler(request, exc: Exception) -> JSONResponse:
    return fail("internal_error", f"{exc.__class__.__name__}: {exc}", status=500)
