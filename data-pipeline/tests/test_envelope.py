import json

from drheri_pipeline.ui import envelope


def _body(resp):
    return json.loads(resp.body.decode("utf-8"))


def test_ok_wraps_data():
    b = _body(envelope.ok({"x": 1}))
    assert b == {"ok": True, "data": {"x": 1}, "error": None}


def test_fail_sets_code_and_status():
    resp = envelope.fail("duplicate_url", "이미 등록된 URL 입니다", status=409)
    assert resp.status_code == 409
    b = _body(resp)
    assert b["ok"] is False
    assert b["error"] == {"code": "duplicate_url", "message": "이미 등록된 URL 입니다"}


def test_api_error_handler_uses_exception_fields():
    exc = envelope.ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    resp = envelope.api_error_handler(None, exc)
    assert resp.status_code == 404
    assert _body(resp)["error"]["code"] == "not_found"
