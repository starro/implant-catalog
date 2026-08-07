"""Dagster 런 상태 센서 → UI 완료 훅 POST.

데몬이 이벤트 기반으로 호출하므로 UI 쪽 폴링 루프가 필요 없다.
UI 를 거치지 않은 직접 실행(document_id=0)은 훅을 보내지 않는다.
"""
import os

import httpx
from dagster import (
    DagsterRunStatus,
    DefaultSensorStatus,
    RunStatusSensorContext,
    run_status_sensor,
)

UI_BASE = os.getenv("UI_BASE_URL", "http://127.0.0.1:3000")
HOOK_TOKEN = os.getenv("HOOK_TOKEN", "drheri-dev")
HOOK_URL = f"{UI_BASE}/api/hooks/run-finished"
OPS = ("catalog_pdf_images", "site_xray_images")


def hook_payload(run_config: dict, status: str, error):
    """런 설정에서 UI 식별자를 뽑아 훅 본문을 만든다. UI 미경유면 None."""
    ops = (run_config or {}).get("ops") or {}
    for name in OPS:
        cfg = (ops.get(name) or {}).get("config") or {}
        ui_run_id = int(cfg.get("ui_run_id") or 0)
        if ui_run_id:
            return {"ui_run_id": ui_run_id,
                    "document_id": int(cfg.get("document_id") or 0),
                    "status": status, "extracted": 0, "error": error}
    return None


def post_hook(payload: dict) -> bool:
    try:
        r = httpx.post(HOOK_URL, json=payload,
                       headers={"X-Hook-Token": HOOK_TOKEN}, timeout=120)
        return 200 <= r.status_code < 300
    except Exception:  # noqa: BLE001
        return False


def _notify(context: RunStatusSensorContext, status: str, error) -> None:
    payload = hook_payload(context.dagster_run.run_config, status, error)
    if payload is None:
        context.log.info("UI 미경유 런 — 훅 생략")
        return
    ok = post_hook(payload)
    context.log.info(f"UI 훅 전송 {'성공' if ok else '실패'} — {payload}")


# default_status 를 주지 않으면 센서가 STOPPED 로 등록되어 사람이 Dagster UI 에서
# 켜기 전까지 발화하지 않는다(개발서버 배포에서 실제로 겪음). 완료 푸시가 이 센서에
# 의존하므로 배포 즉시 동작하도록 RUNNING 으로 등록한다.
@run_status_sensor(run_status=DagsterRunStatus.SUCCESS,
                   default_status=DefaultSensorStatus.RUNNING)
def on_run_success(context: RunStatusSensorContext):
    _notify(context, "SUCCESS", None)


@run_status_sensor(run_status=DagsterRunStatus.FAILURE,
                   default_status=DefaultSensorStatus.RUNNING)
def on_run_failure(context: RunStatusSensorContext):
    err = None
    if context.failure_event and context.failure_event.message:
        err = context.failure_event.message[:500]
    _notify(context, "FAILURE", err)


# Dagster UI 에서 사용자가 수집을 취소하면 CANCELED 가 된다. 이걸 잡아야 관리 UI 의
# run 이 "대기중"에 멈춰 있지 않고 취소로 자동 반영된다(과거엔 30분 타임아웃까지 방치됐음).
@run_status_sensor(run_status=DagsterRunStatus.CANCELED,
                   default_status=DefaultSensorStatus.RUNNING)
def on_run_canceled(context: RunStatusSensorContext):
    _notify(context, "CANCELED", "사용자가 Dagster 에서 취소함")
