import pytest
from starlette.testclient import TestClient

from drheri_pipeline.db import conn, queries
from drheri_pipeline.ui import app as ui_app
from drheri_pipeline.ui.api import runs as runs_api


@pytest.fixture()
def client(data_root, monkeypatch):
    monkeypatch.setattr(runs_api.dagster_client, "submit",
                        lambda **kw: "dagster-run-1")
    monkeypatch.setattr(runs_api.fiftyone_ctl, "restart",
                        lambda: {"ok": True, "orphans_killed": 0, "detail": "OK"})
    return TestClient(ui_app.create_app())


def _doc(client):
    return client.post("/api/sources", json={
        "url": "https://ex.com/a.pdf", "brand": "Osstem", "name": "TS"}).json()["data"]["id"]


def test_collect_creates_run_and_returns_ids(client):
    doc = _doc(client)
    r = client.post(f"/api/sources/{doc}/collect", json={"conf": 0.4, "dpi": 300, "pages": "1,2"})
    data = r.json()["data"]
    assert data["dagster_run_id"] == "dagster-run-1"
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["status"] == "RUNNING"
    assert detail["runs"][0]["dpi"] == 300


def test_collect_uses_document_defaults_when_omitted(client):
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["conf"] == 0.35
    assert detail["runs"][0]["dpi"] == 200


def test_collect_submit_failure_marks_run_failed(client, monkeypatch):
    """브리프 테스트는 성공 경로만 검증한다 — Dagster 제출 실패 시 run 이 FAILURE 로
    남고 에러 메시지가 기록되는지는 실제로 검증되지 않았으므로 보강한다."""
    def _boom(**kw):
        raise RuntimeError("dagster 연결 실패")
    monkeypatch.setattr(runs_api.dagster_client, "submit", _boom)
    doc = _doc(client)
    r = client.post(f"/api/sources/{doc}/collect", json={})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "dagster_submit_failed"
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["status"] == "FAILURE"
    assert "dagster 연결 실패" in detail["runs"][0]["error"]


def test_hook_finishes_run_and_restarts_fiftyone(client, monkeypatch):
    called = {}
    monkeypatch.setattr(runs_api.fiftyone_ctl, "restart",
                        lambda: called.setdefault("restart", True) or
                        {"ok": True, "orphans_killed": 0, "detail": "OK"})
    doc = _doc(client)
    ui_run_id = client.post(f"/api/sources/{doc}/collect", json={}).json()["data"]["ui_run_id"]

    r = client.post("/api/hooks/run-finished",
                    headers={"X-Hook-Token": "drheri-dev"},
                    json={"ui_run_id": ui_run_id, "dagster_run_id": "dagster-run-1",
                          "status": "SUCCESS", "extracted": 9, "error": None})
    assert r.json()["ok"] is True
    assert called["restart"] is True
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["status"] == "SUCCESS"
    assert detail["runs"][0]["extracted"] == 9


def test_hook_rejects_bad_token(client):
    r = client.post("/api/hooks/run-finished", headers={"X-Hook-Token": "wrong"},
                    json={"ui_run_id": 1, "status": "SUCCESS"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_hook_failure_does_not_restart_fiftyone(client, monkeypatch):
    called = {}
    monkeypatch.setattr(runs_api.fiftyone_ctl, "restart",
                        lambda: called.setdefault("restart", True))
    doc = _doc(client)
    ui_run_id = client.post(f"/api/sources/{doc}/collect", json={}).json()["data"]["ui_run_id"]
    client.post("/api/hooks/run-finished", headers={"X-Hook-Token": "drheri-dev"},
                json={"ui_run_id": ui_run_id, "status": "FAILURE",
                      "extracted": 0, "error": "PDF 다운로드 실패"})
    assert "restart" not in called
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["status"] == "FAILURE"
    assert detail["runs"][0]["error"] == "PDF 다운로드 실패"


def test_latest_reconciles_running_run_from_dagster(client, monkeypatch):
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    monkeypatch.setattr(runs_api.dagster_client, "status", lambda rid: "SUCCESS")

    body = client.get(f"/api/sources/{doc}/runs/latest").json()["data"]
    assert body["status"] == "SUCCESS"
    with conn.session() as cx:
        assert queries.running_runs(cx) == []


def test_latest_marks_timeout_after_stall_limit(client, monkeypatch):
    """훅을 놓치고 Dagster 도 끝났다고 말하지 않는 런은 30분 뒤 TIMEOUT 처리한다(스펙 §13)."""
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    monkeypatch.setattr(runs_api.dagster_client, "status", lambda rid: "STARTED")
    with conn.session() as cx:
        cx.execute("UPDATE run SET started_at='2000-01-01T00:00:00+00:00' WHERE document_id=?",
                   (doc,))

    body = client.get(f"/api/sources/{doc}/runs/latest").json()["data"]
    assert body["status"] == "TIMEOUT"


def test_latest_keeps_running_before_stall_limit(client, monkeypatch):
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    monkeypatch.setattr(runs_api.dagster_client, "status", lambda rid: "STARTED")

    body = client.get(f"/api/sources/{doc}/runs/latest").json()["data"]
    assert body["status"] == "RUNNING"
