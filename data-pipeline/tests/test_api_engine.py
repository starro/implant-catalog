from starlette.testclient import TestClient


def test_engine_status_endpoint(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    from drheri_pipeline.ui.api import engine as api_engine
    monkeypatch.setattr(api_engine.engine, "status", lambda: "ready")
    from drheri_pipeline.ui.app import create_app
    c = TestClient(create_app())
    r = c.get("/api/engine/status")
    assert r.status_code == 200 and r.json()["data"]["status"] == "ready"


def test_collect_rejected_when_engine_not_ready(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    from drheri_pipeline.db import conn, writes
    conn.migrate()
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="http://x/a.pdf",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
    from drheri_pipeline.ui.api import runs
    monkeypatch.setattr(runs.engine, "status", lambda: "down")
    from drheri_pipeline.ui.app import create_app
    c = TestClient(create_app())
    r = c.post(f"/api/sources/{d}/collect", json={})
    assert r.status_code == 409
