"""Dr.HERi 데이터 파이프라인 관리 UI (한글) — Starlette + Jinja2.

Dagster/FiftyOne 을 대체하지 않고 앞에 씌우는 컨트롤 플레인:
  - 카탈로그 URL 입력·수집 이력 관리·중복 수집 체크
  - Dagster 잡 실행(GraphQL) + 완료 감지
  - 완료 시 FiftyOne 자동 재기동 (수집분이 라벨링 UI 에 바로 보이도록)
  - 단계별 현황: 중간단계(review) → 학습용(training)

실행: uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000
"""
import asyncio
import os
import subprocess
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from drheri_pipeline import storage
from drheri_pipeline.ui import dagster_client, registry

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
FIFTYONE_URL = os.getenv("FIFTYONE_URL", "http://58.229.105.3:5151")
DAGSTER_URL = os.getenv("DAGSTER_URL", "http://58.229.105.3:3333")
FIFTYONE_SERVICE = os.getenv("FIFTYONE_SERVICE", "drheri-fiftyone")
REPO_DIR = Path(__file__).resolve().parents[2]


def restart_fiftyone() -> str:
    """수집 완료 후 FiftyOne 재기동 — manifest 를 다시 읽어 새 이미지가 보이게."""
    try:
        r = subprocess.run(["sudo", "-n", "systemctl", "restart", FIFTYONE_SERVICE],
                           capture_output=True, text=True, timeout=90)
        return "재기동 완료" if r.returncode == 0 else f"재기동 실패: {(r.stderr or '').strip()[:120]}"
    except Exception as e:  # noqa: BLE001
        return f"재기동 오류: {e}"


async def _watch_run(entry_id: str, run_id: str, url: str) -> None:
    """Dagster 런을 폴링해 끝나면 이력 갱신 + FiftyOne 재기동.

    레지스트리는 append-only 이므로 **상태가 바뀔 때만** 기록한다(폴링마다 쓰면 파일이 비대해짐).
    """
    last = "STARTED"
    for _ in range(360):                       # 최대 ~30분
        await asyncio.sleep(5)
        st = await run_in_threadpool(dagster_client.status, run_id)
        if st in dagster_client.TERMINAL:
            figures = await run_in_threadpool(registry.figures_for_url, url)
            note = await run_in_threadpool(restart_fiftyone) if st == "SUCCESS" else ""
            registry.update(entry_id, status=st, figures=figures, note=note)
            return
        if st != last:                         # 변경 시에만 append
            registry.update(entry_id, status=st)
            last = st
    registry.update(entry_id, status="TIMEOUT")


async def index(request: Request):
    counts = await run_in_threadpool(registry.stage_counts)
    hist = await run_in_threadpool(registry.history)
    running = any(h.get("status") not in dagster_client.TERMINAL | {"TIMEOUT"} for h in hist)
    return TEMPLATES.TemplateResponse("index.html", {
        "request": request, "counts": counts, "history": hist, "running": running,
        "fiftyone_url": FIFTYONE_URL, "dagster_url": DAGSTER_URL,
        "warn": request.query_params.get("warn"),
        "msg": request.query_params.get("msg"),
        "form": dict(request.query_params),
    })


async def collect(request: Request):
    form = await request.form()
    url = (form.get("pdf_url") or "").strip()
    if not url:
        return RedirectResponse("/?msg=URL을 입력하세요", status_code=303)

    brand = (form.get("brand") or "Osstem").strip()
    series = (form.get("series") or "_unknown").strip()
    conf, dpi = float(form.get("conf") or 0.35), int(form.get("dpi") or 200)
    pages = (form.get("pages") or "").strip()
    force = form.get("force") == "1"

    # 중복 수집 체크
    dup = await run_in_threadpool(registry.find_by_url, url)
    if dup and not force:
        d = dup[0]
        warn = f"이미 수집한 URL입니다 ({d.get('created_at','')[:16]}, {d.get('figures',0)}장, 상태 {d.get('status')})"
        from urllib.parse import urlencode
        return RedirectResponse("/?" + urlencode({
            "warn": warn, "pdf_url": url, "brand": brand, "series": series,
            "conf": conf, "dpi": dpi, "pages": pages}), status_code=303)

    try:
        run_id = await run_in_threadpool(dagster_client.submit, url, brand, series, conf, dpi, pages)
    except Exception as e:  # noqa: BLE001
        return RedirectResponse(f"/?msg=실행 실패: {e}", status_code=303)

    entry_id = registry.new_id()
    registry.add({"id": entry_id, "url": url, "brand": brand, "series": series,
                  "conf": conf, "dpi": dpi, "pages": pages, "run_id": run_id,
                  "status": "STARTED", "figures": 0, "created_at": registry.now_iso()})
    asyncio.create_task(_watch_run(entry_id, run_id, url))
    return RedirectResponse("/?msg=수집을 시작했습니다", status_code=303)


async def promote(request: Request):
    """중간단계(review)에서 라벨링된 것 → 학습용(training) 승급."""
    def _run():
        env = {**os.environ, "PYTHONPATH": str(REPO_DIR),
               "DATA_ROOT": str(storage.DATA_ROOT), "FIFTYONE_DATABASE_VALIDATION": "false"}
        r = subprocess.run([str(REPO_DIR / ".venv/bin/python"), str(REPO_DIR / "scripts/promote_reviewed.py")],
                           capture_output=True, text=True, timeout=600, env=env, cwd=str(REPO_DIR))
        return (r.stdout or r.stderr or "").strip().splitlines()[-1:] or ["완료"]
    out = await run_in_threadpool(_run)
    return RedirectResponse(f"/?msg=승급: {out[0][:120]}", status_code=303)


async def health(request: Request):
    return JSONResponse({"ok": True, **await run_in_threadpool(registry.stage_counts)})


app = Starlette(routes=[
    Route("/", index),
    Route("/collect", collect, methods=["POST"]),
    Route("/promote", promote, methods=["POST"]),
    Route("/health", health),
])
