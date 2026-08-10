from drheri_pipeline.ui import engine


class _R:
    def __init__(self, out): self.stdout = out; self.returncode = 0


def test_status_down_when_container_stopped(monkeypatch):
    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **k: _R("false\n"))
    assert engine.status(force=True) == "down"       # force: 4초 캐시 우회하고 로직 검증


def test_status_ready_when_all_healthy(monkeypatch):
    def fake_run(cmd, **k):
        if cmd[:2] == ["docker", "inspect"]:  # running?
            return _R("true\n")
        return _R("200")                      # gdino health (container curl)
    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    monkeypatch.setattr(engine, "_vllm_ok", lambda: True)
    assert engine.status(force=True) == "ready"


def test_status_starting_when_vllm_not_ready(monkeypatch):
    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **k: _R("true\n"))
    monkeypatch.setattr(engine, "_vllm_ok", lambda: False)
    assert engine.status(force=True) == "starting"


def test_status_uses_cache_within_ttl(monkeypatch):
    engine._invalidate()
    calls = {"n": 0}
    def fake_run(cmd, **k):
        calls["n"] += 1
        return _R("false\n")
    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    a = engine.status(force=True)                    # 실제 확인 1회
    n_after_first = calls["n"]
    b = engine.status()                              # 캐시 — subprocess 추가 호출 없어야
    assert a == b == "down" and calls["n"] == n_after_first


def test_up_starts_container_and_gdino(monkeypatch):
    cmds = []
    monkeypatch.setattr(engine, "_running", lambda: False)
    monkeypatch.setattr(engine.subprocess, "run", lambda cmd, **k: cmds.append(cmd) or _R(""))
    engine.up()
    assert any(c[:2] == ["docker", "start"] for c in cmds)
    assert any("gdino_server.py" in " ".join(c) for c in cmds)


def test_down_stops_container(monkeypatch):
    cmds = []
    monkeypatch.setattr(engine.subprocess, "run", lambda cmd, **k: cmds.append(cmd) or _R(""))
    engine.down()
    assert any(c[:2] == ["docker", "stop"] for c in cmds)
