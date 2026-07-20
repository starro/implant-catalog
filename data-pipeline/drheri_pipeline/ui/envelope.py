"""API 응답 봉투 — 모든 라우트가 {ok, data, error} 로만 응답한다."""
from __future__ import annotations

from starlette.responses import JSONResponse


class ApiError(Exception):
    """라우트에서 던지면 봉투 형태로 변환된다."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def ok(data=None, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data, "error": None}, status_code=status)


def fail(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "data": None,
                         "error": {"code": code, "message": message}}, status_code=status)


def api_error_handler(request, exc: ApiError) -> JSONResponse:
    return fail(exc.code, exc.message, exc.status)


def unhandled_error_handler(request, exc: Exception) -> JSONResponse:
    return fail("internal_error", f"{exc.__class__.__name__}: {exc}", status=500)
