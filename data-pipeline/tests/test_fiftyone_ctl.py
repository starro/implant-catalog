from drheri_pipeline.services import fiftyone_ctl


def test_kill_orphans_uses_bracket_patterns_and_spares_mongod(monkeypatch):
    """포트 기준 kill 금지, 자기 자신 매치 방지(브래킷), mongod 보존을 커맨드로 검증."""
    calls = []

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(fiftyone_ctl.subprocess, "run",
                        lambda cmd, **kw: (calls.append(cmd), R())[1])
    fiftyone_ctl.kill_orphans()

    joined = " ".join(" ".join(c) for c in calls)
    assert "mongod" not in joined            # mongod 는 절대 죽이지 않는다
    assert "fuser" not in joined and "lsof" not in joined   # 포트 기준 kill 금지
    for pat in fiftyone_ctl.ORPHAN_PATTERNS:
        assert pat in joined
        assert pat.startswith("[")           # pkill 자기 자신 매치 방지


def test_restart_reports_failure_when_health_fails(monkeypatch):
    monkeypatch.setattr(fiftyone_ctl, "stop", lambda: ["stopped"])
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: 3)
    monkeypatch.setattr(fiftyone_ctl, "start", lambda: None)
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda: {"ok": False, "port": 5151, "detail": "연결 거부"})
    out = fiftyone_ctl.restart()
    assert out["ok"] is False
    assert out["orphans_killed"] == 3
    assert "연결 거부" in out["detail"]


def test_restart_succeeds_when_health_ok(monkeypatch):
    monkeypatch.setattr(fiftyone_ctl, "stop", lambda: ["stopped"])
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: 0)
    monkeypatch.setattr(fiftyone_ctl, "start", lambda: None)
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda: {"ok": True, "port": 5151, "detail": "OK"})
    assert fiftyone_ctl.restart()["ok"] is True
