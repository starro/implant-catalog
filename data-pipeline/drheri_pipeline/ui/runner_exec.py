"""경량 실행기 — Dagster 대체. 컨테이너 엔진을 docker exec 로 돌리고 크롭을 호스트로 cp,
런 tmp 즉시 rm, FiftyOne 등록 + run 종료 + SSE. GPU 공유라 한 번에 1런(전역 락)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess

from drheri_pipeline import storage
from drheri_pipeline.db import conn, writes
from drheri_pipeline.labeling.fiftyone_writer import register_prelabeled
from drheri_pipeline.ui.events import broadcaster

CONTAINER = os.getenv("ENGINE_CONTAINER", "vllm-shlee")
ENGINE_PYTHONPATH = "/engine"

_run_lock = asyncio.Lock()


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


def _read_container_manifest(run_id: int) -> list[dict]:
    """컨테이너 tmp 의 이번 런 manifest.jsonl 을 직접 읽는다(호스트 cp 덮어쓰기와 무관)."""
    r = subprocess.run(["docker", "exec", CONTAINER, "cat", f"{tmp_dir(run_id)}/manifest.jsonl"],
                       capture_output=True, text=True)
    out = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _record(records: list[dict], document_id: int, run_id: int) -> int:
    if not records:
        return 0
    with conn.session() as cx:
        for r in records:
            writes.record_image(cx, r, document_id, run_id)
        cx.execute("UPDATE run SET extracted=? WHERE id=?", (len(records), run_id))
    return len(records)


def _set_running(run_id: int) -> None:
    with conn.session() as cx:
        cx.execute("UPDATE run SET status='RUNNING' WHERE id=?", (run_id,))


def _finalize_success(run_id: int, doc_id: int, log) -> int:
    """엔진 성공 후 동기 후처리(스레드에서 실행) — cp·manifest 누적·DB 기록·FiftyOne 등록."""
    prior = storage.MANIFEST.read_text(encoding="utf-8") if storage.MANIFEST.exists() else ""
    records = _read_container_manifest(run_id)
    subprocess.run(cp_cmd(run_id), check=True)          # 크롭 병합(+ manifest 는 이번 런 것으로 덮임)
    storage.MANIFEST.write_text(prior, encoding="utf-8")  # cp 가 덮은 것 되돌리고
    storage.append_manifest(records)                    # 이번 런 레코드 누적 append
    extracted = _record(records, doc_id, run_id)
    register_prelabeled(records, log=log)
    return extracted


def _finish(run_id: int, status: str, extracted: int, error: str | None) -> None:
    with conn.session() as cx:
        writes.finish_run(cx, run_id, status, extracted, error)


async def run_engine(doc_id: int, run_id: int, pdf: str, brand: str, pages: str,
                     dpi: int, conf_min: float, log=print) -> None:
    async with _run_lock:
        await asyncio.to_thread(_set_running, run_id)
        status, extracted, error = "SUCCESS", 0, None
        try:
            proc = await asyncio.create_subprocess_exec(*exec_cmd(run_id, pdf, brand, pages, dpi, conf_min))
            rc = await proc.wait()
            if rc != 0:
                raise RuntimeError(f"engine exit {rc}")
            extracted = await asyncio.to_thread(_finalize_success, run_id, doc_id, log)
        except Exception as e:  # noqa: BLE001
            status, error = "FAILURE", f"{e.__class__.__name__}: {e}"
        finally:
            await asyncio.to_thread(subprocess.run, rm_cmd(run_id), check=False)   # 성공/실패 무관 즉시 정리
        await asyncio.to_thread(_finish, run_id, status, extracted, error)
        broadcaster.publish("run.finished", {
            "ui_run_id": run_id, "document_id": doc_id, "status": status,
            "extracted": extracted, "error": error})
