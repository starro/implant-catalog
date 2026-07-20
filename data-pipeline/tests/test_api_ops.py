import pytest
from starlette.testclient import TestClient

from drheri_pipeline.ui import app as ui_app
from drheri_pipeline.ui.api import ops as ops_api


@pytest.fixture()
def client(data_root):
    return TestClient(ui_app.create_app())


def test_sync_returns_counts_and_publishes_event(client, monkeypatch):
    monkeypatch.setattr(ops_api.sync, "run_sync",
                        lambda: {"kept": 3, "rejected": 1, "promoted": 2, "note": "샘플 4건 확인"})
    published = []
    monkeypatch.setattr(ops_api.broadcaster, "publish",
                        lambda e, p: published.append((e, p)))
    body = client.post("/api/sync").json()
    assert body["data"]["promoted"] == 2
    assert published[0][0] == "sync.finished"


def test_sync_rejects_concurrent_run(client, monkeypatch):
    monkeypatch.setattr(ops_api, "_sync_running", True)
    r = client.post("/api/sync")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "sync_in_progress"


def test_sync_flag_resets_after_completion_allowing_rerun(client, monkeypatch):
    """브리프 테스트는 _sync_running 을 직접 True 로 찍어 409 인지만 본다 — 실제 실행 경로가
    끝난 뒤 플래그가 확실히 해제돼 재실행 가능한지는 검증하지 않는다. 두 번 연달아 성공해야 한다."""
    monkeypatch.setattr(ops_api.sync, "run_sync",
                        lambda: {"kept": 0, "rejected": 0, "promoted": 0, "note": "ok"})
    r1 = client.post("/api/sync")
    assert r1.status_code == 200
    assert ops_api._sync_running is False
    r2 = client.post("/api/sync")
    assert r2.status_code == 200


def test_sync_flag_resets_after_exception(client, monkeypatch):
    """run_sync 가 예외를 던져도 finally 로 플래그가 풀려야 다음 실행이 영구히 막히지 않는다.

    TestClient 는 기본적으로(raise_server_exceptions=True) 서버측 예외를 그대로 재발생시키므로
    500 응답 바디 대신 예외 자체를 pytest.raises 로 받는다.
    """
    def _boom():
        raise RuntimeError("동기화 실패")
    monkeypatch.setattr(ops_api.sync, "run_sync", _boom)
    with pytest.raises(RuntimeError):
        client.post("/api/sync")
    assert ops_api._sync_running is False

    monkeypatch.setattr(ops_api.sync, "run_sync",
                        lambda: {"kept": 0, "rejected": 0, "promoted": 0, "note": "ok"})
    r2 = client.post("/api/sync")
    assert r2.status_code == 200


def test_overview_returns_funnel_and_recent_runs(client):
    data = client.get("/api/overview").json()["data"]
    assert data["funnel"]["extracted"] == 0
    assert data["recent_runs"] == []
    assert "services" in data


def test_export_writes_files(client):
    data = client.post("/api/export").json()["data"]
    assert data["rows"] == 0
    assert data["labels_tsv"].endswith("labels.tsv")

    summary = client.get("/api/export/summary").json()["data"]
    assert summary["total"] == 0


def test_settings_roundtrip(client):
    before = client.get("/api/settings").json()["data"]
    assert "DEFAULT_CONF" in before
    client.post("/api/settings", json={"DEFAULT_CONF": "0.5"})
    after = client.get("/api/settings").json()["data"]
    assert after["DEFAULT_CONF"] == "0.5"


def test_fiftyone_restart_route(client, monkeypatch):
    monkeypatch.setattr(ops_api.fiftyone_ctl, "restart",
                        lambda: {"ok": True, "orphans_killed": 2, "detail": "OK"})
    body = client.post("/api/fiftyone/restart").json()
    assert body["data"]["orphans_killed"] == 2


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["data"]["db"] is True
