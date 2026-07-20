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
import urllib.error
import urllib.request

SERVICE = os.getenv("FIFTYONE_SERVICE", "drheri-fiftyone")
PORT = int(os.getenv("FIFTYONE_PORT", "5151"))
HEALTH_URL = os.getenv("FIFTYONE_HEALTH_URL", f"http://127.0.0.1:{PORT}/")

# 브래킷 표기: pkill -f "[f]iftyone.server" 는 자기 자신의 cmdline 과 매치되지 않는다.
ORPHAN_PATTERNS = ["[f]iftyone.server", "[f]iftyone.core.service", "[s]erve_fiftyone_service"]


def _run(cmd: list[str], timeout: int = 60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def stop() -> list[str]:
    r = _run(["sudo", "-n", "systemctl", "stop", SERVICE], timeout=90)
    return [f"systemctl stop {SERVICE} → rc={r.returncode} {(r.stderr or '').strip()[:120]}"]


def kill_orphans() -> int:
    """cmdline 패턴으로 잔여 프로세스를 종료. 종료시킨 패턴 수를 반환."""
    killed = 0
    for pat in ORPHAN_PATTERNS:
        r = _run(["pkill", "-TERM", "-f", pat])
        if r.returncode == 0:                 # 0 = 하나 이상 종료됨
            killed += 1
    for pat in ORPHAN_PATTERNS:               # TERM 으로 안 죽은 것만 KILL
        _run(["pkill", "-KILL", "-f", pat])
    return killed


def start() -> None:
    _run(["sudo", "-n", "systemctl", "start", SERVICE], timeout=90)


def health() -> dict:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as resp:
            ok = 200 <= resp.status < 400
            return {"ok": ok, "port": PORT, "detail": f"HTTP {resp.status}"}
    except urllib.error.URLError as e:
        return {"ok": False, "port": PORT, "detail": f"연결 실패: {e.reason}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "port": PORT, "detail": f"{e.__class__.__name__}: {e}"}


def restart() -> dict:
    """정지 → 좀비정리 → 기동 → 헬스체크. 수동 버튼과 완료 훅이 공유하는 유일한 경로."""
    detail = stop()
    orphans = kill_orphans()
    start()
    h = health()
    detail.append(f"잔여 프로세스 정리 {orphans}건")
    detail.append(h["detail"])
    return {"ok": h["ok"], "orphans_killed": orphans, "detail": " / ".join(detail)}
