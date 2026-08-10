import asyncio
from starlette.testclient import TestClient


def test_collect_starts_engine(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    from drheri_pipeline.db import conn, writes
    conn.migrate()
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="http://x/a.pdf",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
    started = {}
    async def fake_run_engine(doc_id, run_id, pdf, brand, pages, dpi, conf_min, log=print):
        started.update(doc_id=doc_id, run_id=run_id, pdf=pdf, brand=brand)
    from drheri_pipeline.ui.api import runs
    monkeypatch.setattr(runs.runner_exec, "run_engine", fake_run_engine)
    monkeypatch.setattr(runs.engine, "status", lambda: "ready")
    from drheri_pipeline.ui.app import create_app
    client = TestClient(create_app())
    r = client.post(f"/api/sources/{d}/collect", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["data"]["ui_run_id"]
    # async task 가 실제로 스케줄됐는지 — 짧게 이벤트루프 양보
    import time; time.sleep(0.05)
    assert started.get("brand") == "BEGO"
