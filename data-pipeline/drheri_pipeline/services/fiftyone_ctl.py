"""FiftyOne 서비스 제어 — 정지 → 좀비정리 → 기동 → 헬스체크.

과거 사고: 앱 하나당 파이썬 프로세스가 여러 개 남아, 포트만 죽이는 방식으로는
자식 세션이 살아남아 데이터셋이 주기적으로 초기화됐다. 그래서
  - 포트 기준 kill(fuser/lsof) 을 쓰지 않는다
  - cmdline 패턴으로 프로세스 트리를 잡는다
  - pkill 이 자기 자신을 매치하지 않도록 브래킷 표기를 쓴다
  - mongod 는 절대 죽이지 않는다 (데이터 유실)
"""
from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request

# 브래킷 표기: pkill -f "[f]iftyone.server" 는 자기 자신의 cmdline 과 매치되지 않는다.
ORPHAN_PATTERNS = ["[f]iftyone.server", "[f]iftyone.core.service", "[s]erve_fiftyone_service"]

# 재기동 후 헬스체크를 기다리는 최대 시간(초). 개발서버 실측 기동 시간이 ~60초라 여유를 둔다.
STARTUP_WAIT_S = int(os.getenv("FIFTYONE_STARTUP_WAIT_S", "120"))


def _service() -> str:
    """호출 시점에 환경변수를 읽는다 — 설정 화면에서 바꾼 값이 즉시 반영되도록."""
    return os.getenv("FIFTYONE_SERVICE", "drheri-fiftyone")


def _port() -> int:
    return int(os.getenv("FIFTYONE_PORT", "5151"))


def _health_url() -> str:
    return os.getenv("FIFTYONE_HEALTH_URL", f"http://127.0.0.1:{_port()}/")


def _run(cmd: list[str], timeout: int = 60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def stop() -> dict:
    """FiftyOne 서비스 정지. 반환: {"ok": bool, "lines": [...]}.

    ok=False 는 systemctl 실패(예: sudoers 화이트리스트에 없는 verb 로 인한 sudo 거부)를 뜻한다.
    restart() 는 이 값을 보고 kill_orphans() 강행 여부를 결정한다(안전장치, 아래 참고).
    """
    service = _service()
    r = _run(["sudo", "-n", "systemctl", "stop", service], timeout=90)
    return {"ok": r.returncode == 0,
            "lines": [f"systemctl stop {service} → rc={r.returncode} {(r.stderr or '').strip()[:120]}"]}


def kill_orphans() -> int:
    """cmdline 패턴으로 잔여 프로세스를 종료. 종료 대상이 된 실제 프로세스 수를 반환.

    kill 신호를 보내기 전에 pgrep 으로 매칭되는 PID 개수를 세어 합산한다
    (pkill 의 반환코드는 "하나 이상 매칭됐는지"만 알려줄 뿐 개수를 주지 않는다).
    """
    killed = 0
    for pat in ORPHAN_PATTERNS:
        r = _run(["pgrep", "-f", pat])
        killed += len([p for p in (r.stdout or "").split() if p])
    for pat in ORPHAN_PATTERNS:
        _run(["pkill", "-TERM", "-f", pat])
    for pat in ORPHAN_PATTERNS:               # 생존여부 재확인 없이 곧바로 KILL 로 마무리한다.
        _run(["pkill", "-KILL", "-f", pat])   # 과거 사고(좀비 잔존) 재발을 막기 위해 항상 확실히 죽인다.
    return killed


def start() -> dict:
    """FiftyOne 서비스 기동. 반환: {"ok": bool, "lines": [...]}.

    과거엔 반환값을 통째로 버려서(None) sudo 거부 같은 명백한 실패도 restart() 결과에 반영되지 않았다.
    """
    service = _service()
    r = _run(["sudo", "-n", "systemctl", "start", service], timeout=90)
    return {"ok": r.returncode == 0,
            "lines": [f"systemctl start {service} → rc={r.returncode} {(r.stderr or '').strip()[:120]}"]}


def _probe() -> dict:
    """5151 에 한 번 요청해 본다."""
    port = _port()
    try:
        with urllib.request.urlopen(_health_url(), timeout=10) as resp:
            ok = 200 <= resp.status < 400
            return {"ok": ok, "port": port, "detail": f"HTTP {resp.status}"}
    except urllib.error.URLError as e:
        return {"ok": False, "port": port, "detail": f"연결 실패: {e.reason}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "port": port, "detail": f"{e.__class__.__name__}: {e}"}


def health(wait_s: int = 0, interval_s: float = 3.0) -> dict:
    """헬스체크. wait_s 를 주면 그 시간까지 재시도한다.

    FiftyOne 은 데이터셋을 읽느라 기동에 1분 안팎이 걸린다(개발서버 실측 ~60초).
    재기동 직후 한 번만 찔러보면 항상 실패로 보고되므로 대기가 필요하다.
    현황 조회처럼 즉답이 필요한 곳은 기본값(wait_s=0)으로 쓴다.
    """
    deadline = time.monotonic() + max(0, wait_s)
    while True:
        result = _probe()
        if result["ok"] or time.monotonic() >= deadline:
            return result
        time.sleep(interval_s)


def restart() -> dict:
    """정지 → 좀비정리 → 기동 → 헬스체크. 수동 버튼과 완료 훅이 공유하는 유일한 경로.

    안전장치: stop() 이 실패하면(sudoers 화이트리스트 누락 등) kill_orphans() 를 호출하지 않고
    즉시 실패를 반환한다. 서비스를 정상적으로 멈추지 못한 상태에서 좀비 프로세스만 강제 종료하면,
    systemd 는 재기동을 시도하지 않으므로 FiftyOne 이 내려간 채로 남는 사고가 그대로 재현된다.
    """
    stop_result = stop()
    detail = list(stop_result["lines"])
    if not stop_result["ok"]:
        detail.append("stop 실패 — 강제종료(kill_orphans) 생략")
        return {"ok": False, "orphans_killed": 0, "detail": " / ".join(detail)}

    orphans = kill_orphans()
    start_result = start()
    detail += start_result["lines"]
    # 기동 직후 한 번만 찔러보면 항상 실패로 나온다(개발서버 실측 기동 시간 ~60초).
    h = health(wait_s=STARTUP_WAIT_S)
    detail.append(f"잔여 프로세스 정리 {orphans}건")
    detail.append(h["detail"])
    ok = start_result["ok"] and h["ok"]
    return {"ok": ok, "orphans_killed": orphans, "detail": " / ".join(detail)}
