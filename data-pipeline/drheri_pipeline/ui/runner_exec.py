"""경량 실행기 — Dagster 대체. 컨테이너 엔진을 docker exec 로 돌리고 크롭을 호스트로 cp,
런 tmp 즉시 rm, FiftyOne 등록 + run 종료 + SSE. GPU 공유라 한 번에 1런(전역 락)."""
from __future__ import annotations

import asyncio
import os

from drheri_pipeline import storage

CONTAINER = os.getenv("ENGINE_CONTAINER", "vllm-shlee")
ENGINE_PYTHONPATH = "/engine"


def tmp_dir(run_id: int) -> str:
    return f"/engine/run_{run_id}"


def exec_cmd(run_id: int, pdf: str, brand: str, pages: str, dpi: int, conf_min: float) -> list[str]:
    inner = (f"PYTHONPATH={ENGINE_PYTHONPATH} DATA_ROOT={tmp_dir(run_id)} "
             f"python -m drheri_pipeline.labeling.cli "
             f"--pdf {pdf!r} --brand {brand!r} --dpi {int(dpi)} --conf-min {float(conf_min)}")
    if pages:
        inner += f" --pages {pages!r}"
    return ["docker", "exec", CONTAINER, "bash", "-lc", inner]


def cp_cmd(run_id: int) -> list[str]:
    return ["docker", "cp", f"{CONTAINER}:{tmp_dir(run_id)}/.", str(storage.DATA_ROOT)]


def rm_cmd(run_id: int) -> list[str]:
    return ["docker", "exec", CONTAINER, "rm", "-rf", tmp_dir(run_id)]
