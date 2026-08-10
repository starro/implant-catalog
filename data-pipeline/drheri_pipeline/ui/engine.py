"""엔진 전원 제어 — vllm-shlee 컨테이너(vLLM+GDINO) 켜기/끄기/상태.
UI에서 명시적 조작. 수집 안 할 땐 내려 GPU(~44GB)를 다른 계정 학습에 양보."""
from __future__ import annotations

import subprocess
import time

import httpx

from drheri_pipeline.ui.runner_exec import CONTAINER

_VLLM_URL = "http://127.0.0.1:8000/v1/models"

_STATUS_TTL = 4.0                          # status() 결과 캐시 — UI 가 2초마다(탭마다) 폴링해도
_status_cache = {"t": -1e9, "val": "down"}  # docker exec/추론을 매번 돌리지 않게


def _running() -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
                       capture_output=True, text=True)
    return r.stdout.strip() == "true"


def _vllm_ok() -> bool:
    try:
        return httpx.get(_VLLM_URL, timeout=3).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _gdino_ok() -> bool:
    # /health 는 tiny 실추론까지 돌린다 — 프로세스만 살아있고 cuDNN 이 죽은 상태를 걸러낸다.
    # 고장이면 서버가 자가복구(모델 재로드)를 시도하므로 재로드 시간(~15s)까지 대기.
    r = subprocess.run(
        ["docker", "exec", CONTAINER, "curl", "-s", "-o", "/dev/null",
         "-w", "%{http_code}", "--max-time", "15", "http://127.0.0.1:8100/health"],
        capture_output=True, text=True)
    return r.stdout.strip() == "200"


def _invalidate() -> None:
    _status_cache["t"] = -1e9


def status(force: bool = False) -> str:
    now = time.monotonic()
    if not force and (now - _status_cache["t"]) < _STATUS_TTL:
        return _status_cache["val"]                  # 캐시 유효 — docker exec/추론 생략
    if not _running():
        val = "down"
    else:
        val = "ready" if (_vllm_ok() and _gdino_ok()) else "starting"
    _status_cache["t"] = now
    _status_cache["val"] = val
    return val


def up() -> None:
    """컨테이너 start + GDINO 서비스 기동. 즉시 반환(웜업은 백그라운드). 이미 떠 있어도 무해."""
    if not _running():
        subprocess.run(["docker", "start", CONTAINER], check=True)
    subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-lc",
                    "python /engine/gdino_server.py > /tmp/gdino.log 2>&1"], check=False)
    _invalidate()                                    # 방금 켰으니 다음 status 는 새로 확인


def down() -> None:
    subprocess.run(["docker", "stop", CONTAINER], check=False)
    _invalidate()
