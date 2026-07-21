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
    monkeypatch.setattr(fiftyone_ctl, "stop", lambda: {"ok": True, "lines": ["stopped"]})
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: 3)
    monkeypatch.setattr(fiftyone_ctl, "start", lambda: {"ok": True, "lines": ["started"]})
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda wait_s=0, interval_s=3.0: {"ok": False, "port": 5151, "detail": "연결 거부"})
    out = fiftyone_ctl.restart()
    assert out["ok"] is False
    assert out["orphans_killed"] == 3
    assert "연결 거부" in out["detail"]


def test_restart_succeeds_when_health_ok(monkeypatch):
    monkeypatch.setattr(fiftyone_ctl, "stop", lambda: {"ok": True, "lines": ["stopped"]})
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: 0)
    monkeypatch.setattr(fiftyone_ctl, "start", lambda: {"ok": True, "lines": ["started"]})
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda wait_s=0, interval_s=3.0: {"ok": True, "port": 5151, "detail": "OK"})
    assert fiftyone_ctl.restart()["ok"] is True


def test_restart_calls_stop_kill_orphans_start_health_in_order(monkeypatch):
    """스텁을 각각 교체하는 것만으로는 순서가 뒤바뀌어도 통과한다 — 실제 호출 순서를 기록해 검증."""
    order = []
    monkeypatch.setattr(fiftyone_ctl, "stop",
                        lambda: (order.append("stop"), {"ok": True, "lines": ["stopped"]})[1])
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans",
                        lambda: (order.append("kill_orphans"), 0)[1])
    monkeypatch.setattr(fiftyone_ctl, "start",
                        lambda: (order.append("start"), {"ok": True, "lines": ["started"]})[1])
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda wait_s=0, interval_s=3.0: (order.append("health"),
                                                          {"ok": True, "port": 5151,
                                                           "detail": "OK"})[1])

    fiftyone_ctl.restart()

    assert order == ["stop", "kill_orphans", "start", "health"]


def test_restart_skips_kill_orphans_and_start_when_stop_fails(monkeypatch):
    """Critical 1 안전장치: stop() 이 실패(sudo 거부 등, returncode!=0)하면 kill_orphans() 를
    호출하지 않고 즉시 ok=False 를 반환해야 한다. 서비스를 못 멈춘 채 좀비만 죽이면
    systemd 가 재기동을 시도하지 않아 FiftyOne 이 내려간 채로 남는 사고가 재현된다."""
    class R:
        returncode = 1
        stdout = ""
        stderr = "sudo: a password is required"

    monkeypatch.setattr(fiftyone_ctl.subprocess, "run", lambda cmd, **kw: R())

    calls = []
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: calls.append("kill_orphans") or 0)
    monkeypatch.setattr(fiftyone_ctl, "start",
                        lambda: calls.append("start") or {"ok": True, "lines": []})
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda: calls.append("health") or {"ok": True, "port": 5151, "detail": "OK"})

    out = fiftyone_ctl.restart()

    assert out["ok"] is False
    assert out["orphans_killed"] == 0
    assert calls == []                    # kill_orphans/start/health 어느 것도 호출되면 안 된다
    assert "rc=1" in out["detail"]


def test_kill_orphans_returns_pid_count_from_pgrep_not_pattern_count(monkeypatch):
    """계약은 '종료시킨 프로세스 수'다 — 패턴 개수(최대 3)가 아니라 pgrep 이 찾은 PID 개수를 세야 한다."""
    pat1, pat2, pat3 = fiftyone_ctl.ORPHAN_PATTERNS
    pid_output = {pat1: "111\n222\n", pat2: "", pat3: "333\n"}  # 2 + 0 + 1 = 3 PID, 패턴은 3개 다 매치

    class R:
        def __init__(self, stdout=""):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(cmd, **kw):
        if cmd[0] == "pgrep":
            return R(pid_output.get(cmd[-1], ""))
        return R()

    monkeypatch.setattr(fiftyone_ctl.subprocess, "run", fake_run)
    n = fiftyone_ctl.kill_orphans()

    assert n == 3


def test_stop_uses_current_env_service_name_not_import_time_value(monkeypatch):
    """FIFTYONE_SERVICE 를 런타임에 바꾸면 즉시 반영돼야 한다 — 모듈 import 시점 상수면 안 된다.

    설정 화면에서 서비스명을 바꿔도 fiftyone_ctl 이 모듈 로드 시점에 고정된 이름을 쓰면
    응답은 성공으로 오지만 실제 systemctl 대상은 바뀌지 않는 버그(A-1)를 검증한다.
    """
    monkeypatch.setenv("FIFTYONE_SERVICE", "custom-fiftyone-svc")

    calls = []

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(fiftyone_ctl.subprocess, "run",
                        lambda cmd, **kw: (calls.append(cmd), R())[1])
    fiftyone_ctl.stop()

    joined = " ".join(" ".join(c) for c in calls)
    assert "custom-fiftyone-svc" in joined
    assert "drheri-fiftyone" not in joined


def test_health_retries_until_service_is_up(monkeypatch):
    """FiftyOne 은 기동에 1분 안팎 걸린다. 즉시 한 번만 찔러보면 항상 실패로 보고된다."""
    attempts = []

    def fake_probe():
        attempts.append(1)
        ok = len(attempts) >= 3          # 세 번째 시도에 뜬다
        return {"ok": ok, "port": 5151, "detail": "HTTP 200" if ok else "연결 실패: refused"}

    monkeypatch.setattr(fiftyone_ctl, "_probe", fake_probe)
    monkeypatch.setattr(fiftyone_ctl.time, "sleep", lambda s: None)

    out = fiftyone_ctl.health(wait_s=60, interval_s=0.01)
    assert out["ok"] is True
    assert len(attempts) == 3


def test_health_without_wait_probes_once(monkeypatch):
    """현황 조회처럼 즉답이 필요한 곳은 기다리지 않는다."""
    attempts = []
    monkeypatch.setattr(fiftyone_ctl, "_probe",
                        lambda: (attempts.append(1),
                                 {"ok": False, "port": 5151, "detail": "연결 실패: refused"})[1])
    monkeypatch.setattr(fiftyone_ctl.time, "sleep", lambda s: None)

    assert fiftyone_ctl.health()["ok"] is False
    assert len(attempts) == 1


def test_restart_waits_for_startup_before_reporting_failure(monkeypatch):
    """재기동 결과가 '기동 대기'를 거친 헬스체크를 반영해야 한다."""
    waited = {}
    monkeypatch.setattr(fiftyone_ctl, "stop", lambda: {"ok": True, "lines": ["stopped"]})
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: 0)
    monkeypatch.setattr(fiftyone_ctl, "start", lambda: {"ok": True, "lines": ["started"]})
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda wait_s=0, interval_s=3.0: (waited.update(wait_s=wait_s),
                                                          {"ok": True, "port": 5151,
                                                           "detail": "HTTP 200"})[1])
    assert fiftyone_ctl.restart()["ok"] is True
    assert waited["wait_s"] > 0
