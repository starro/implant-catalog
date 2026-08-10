from drheri_pipeline.ui import runner_exec as R


def test_exec_cmd_shape():
    cmd = R.exec_cmd(7, "/engine/run_7/src.pdf", "BEGO", "12-26", 200, 0.6)
    assert cmd[:3] == ["docker", "exec", R.CONTAINER]
    # inner command is composed as a single "bash -lc <script>" element, not split tokens
    joined = " ".join(cmd)
    assert "-m" in joined and "drheri_pipeline.labeling.cli" in joined
    assert "--pdf" in joined and "/engine/run_7/src.pdf" in joined
    assert "--brand" in joined and "BEGO" in joined
    assert "--pages" in joined and "12-26" in joined
    # DATA_ROOT 은 런별 tmp 로
    assert "DATA_ROOT=/engine/run_7" in joined


def test_exec_cmd_omits_empty_pages():
    cmd = R.exec_cmd(7, "http://x/a.pdf", "BEGO", "", 200, 0.6)
    assert "--pages" not in " ".join(cmd)


def test_cp_and_rm_cmd(monkeypatch, tmp_path):
    from drheri_pipeline import storage
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    cp = R.cp_cmd(7)
    assert cp[:2] == ["docker", "cp"]
    assert f"{R.CONTAINER}:/engine/run_7/." in cp
    assert str(tmp_path) in " ".join(cp)
    rm = R.rm_cmd(7)
    assert rm[:3] == ["docker", "exec", R.CONTAINER] and "rm" in rm and "/engine/run_7" in " ".join(rm)


import asyncio, json
from drheri_pipeline.ui import runner_exec as R


class _Proc:
    def __init__(self, rc): self.returncode = rc
    async def wait(self): return self.returncode
    async def communicate(self): return (b"", b"")


def _setup(tmp_path, monkeypatch, rc=0, recs=None):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(storage, "MANIFEST", tmp_path / "manifest.jsonl")
    conn.migrate()
    async def fake_exec(*a, **k): return _Proc(rc)
    monkeypatch.setattr(R.asyncio, "create_subprocess_exec", fake_exec)
    calls = {"cp": 0, "rm": 0, "cat": 0}
    def fake_run(cmd, **k):
        if "cat" in cmd:
            calls["cat"] += 1
            # 컨테이너의 이번 런 manifest.jsonl 을 직접 읽어온 것처럼 준비
            class R3:
                stdout = "\n".join(json.dumps(r) for r in (recs or []))
                stderr = ""
                returncode = 0
            return R3()
        if cmd[:2] == ["docker", "cp"]:
            calls["cp"] += 1
            # docker cp 가 호스트 manifest 를 이번 런 것으로 덮어쓰는 것처럼 재현(클로버)
            (tmp_path / "manifest.jsonl").write_text(
                "\n".join(json.dumps(r) for r in (recs or [])), encoding="utf-8")
        if "rm" in cmd:
            calls["rm"] += 1
        class R2: returncode = 0
        return R2()
    monkeypatch.setattr(R.subprocess, "run", fake_run)
    reg = {"n": 0}
    monkeypatch.setattr(R, "register_prelabeled", lambda records, log=print: reg.__setitem__("n", len(records)) or len(records))
    events = []
    monkeypatch.setattr(R.broadcaster, "publish", lambda t, p: events.append((t, p)))
    return calls, reg, events


def test_run_engine_success(tmp_path, monkeypatch):
    from drheri_pipeline.db import conn, writes
    from drheri_pipeline import storage
    recs = [{"content_hash": "h1", "path": "review/BEGO/catalog/h1.png", "brand": "BEGO",
             "is_fixture": True, "diameter": "4.1", "diameter_src": "geom",
             "needs_review": False, "page_no": 1, "bbox": [1, 2, 3, 4]}]
    calls, reg, events = _setup(tmp_path, monkeypatch, rc=0, recs=recs)
    # 이전 런에서 이미 누적돼 있던 매니페스트 레코드 (덮어쓰기로 유실되면 안 됨)
    prior_rec = {"content_hash": "h0", "path": "review/BEGO/catalog/h0.png", "brand": "BEGO",
                 "is_fixture": True, "diameter": "3.5", "diameter_src": "geom",
                 "needs_review": False, "page_no": 1, "bbox": [0, 0, 1, 1]}
    storage.append_manifest([prior_rec])
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u1",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        run_id = writes.create_run(cx, d, 0.3, 200, "")
    asyncio.run(R.run_engine(d, run_id, "http://x/a.pdf", "BEGO", "", 200, 0.6))
    cx = conn.connect()
    st = cx.execute("SELECT status FROM run WHERE id=?", (run_id,)).fetchone()["status"]
    cx.close()
    assert st == "SUCCESS" and reg["n"] == 1 and calls["rm"] == 1
    assert any(t == "run.finished" for t, _ in events)
    # 매니페스트는 덮어써지지 않고 누적된다: 이전 1건 + 이번 런 1건
    manifest = storage.read_manifest()
    assert len(manifest) == 1 + len(recs)
    assert {r["content_hash"] for r in manifest} == {"h0", "h1"}


def test_run_engine_failure_still_cleans_up(tmp_path, monkeypatch):
    from drheri_pipeline.db import conn, writes
    calls, reg, events = _setup(tmp_path, monkeypatch, rc=1, recs=[])
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u2",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        run_id = writes.create_run(cx, d, 0.3, 200, "")
    asyncio.run(R.run_engine(d, run_id, "http://x/a.pdf", "BEGO", "", 200, 0.6))
    cx = conn.connect()
    st = cx.execute("SELECT status FROM run WHERE id=?", (run_id,)).fetchone()["status"]
    cx.close()
    assert st == "FAILURE" and calls["rm"] == 1     # 실패해도 tmp 정리


def test_prepare_pdf_url_passthrough():
    assert R._prepare_pdf(7, "http://x/a.pdf") == "http://x/a.pdf"
    assert R._prepare_pdf(7, "https://x/a.pdf") == "https://x/a.pdf"


def test_prepare_pdf_injects_host_file(tmp_path, monkeypatch):
    f = tmp_path / "up.pdf"; f.write_bytes(b"%PDF")
    calls = []
    def fake_run(cmd, **k):
        calls.append(cmd)
        class R2: returncode = 0
        return R2()
    monkeypatch.setattr(R.subprocess, "run", fake_run)
    out = R._prepare_pdf(7, str(f))
    assert out == "/engine/run_7_src.pdf"
    assert calls and calls[0][:2] == ["docker", "cp"] and str(f) in calls[0]


def test_prepare_pdf_container_path_passthrough():
    # 호스트에 없는 경로(컨테이너 로컬 등) → 그대로
    assert R._prepare_pdf(7, "/nonexistent-container-only.pdf") == "/nonexistent-container-only.pdf"


def test_rm_cmd_cleans_injected_src():
    rm = R.rm_cmd(7)
    j = " ".join(rm)
    assert "/engine/run_7" in j and "/engine/run_7_src.pdf" in j
