"""엔진 전원 제어 — vllm-shlee 컨테이너(vLLM+GDINO) 켜기/끄기/상태.
UI에서 명시적 조작. 수집 안 할 땐 내려 GPU(~44GB)를 다른 계정 학습에 양보."""
from __future__ import annotations

import subprocess

import httpx

from drheri_pipeline.ui.runner_exec import CONTAINER

_VLLM_URL = "http://127.0.0.1:8000/v1/models"


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
         "-w", "%{http_code}", "--max-time", "40", "http://127.0.0.1:8100/health"],
        capture_output=True, text=True)
    return r.stdout.strip() == "200"


def status() -> str:
    if not _running():
        return "down"
    return "ready" if (_vllm_ok() and _gdino_ok()) else "starting"


def up() -> None:
    """컨테이너 start + GDINO 서비스 기동. 즉시 반환(웜업은 백그라운드). 이미 떠 있어도 무해."""
    if not _running():
        subprocess.run(["docker", "start", CONTAINER], check=True)
    subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-lc",
                    "python /engine/gdino_server.py > /tmp/gdino.log 2>&1"], check=False)


def down() -> None:
    subprocess.run(["docker", "stop", CONTAINER], check=False)
