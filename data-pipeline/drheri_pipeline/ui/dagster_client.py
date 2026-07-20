"""Dagster 실행 엔진 호출 — GraphQL 클라이언트 래퍼.

UI 는 YAML Launchpad 대신 이걸로 잡을 제출/상태조회한다. (Dagster 는 그대로 엔진 역할)
"""
import os

from dagster_graphql import DagsterGraphQLClient

HOST = os.getenv("DAGSTER_HOST", "localhost")
PORT = int(os.getenv("DAGSTER_UI_PORT", "3333"))
JOB = "ingest_catalog_pdf"

TERMINAL = {"SUCCESS", "FAILURE", "CANCELED"}


def _client() -> DagsterGraphQLClient:
    return DagsterGraphQLClient(HOST, port_number=PORT)


def submit(*, pdf_url: str, brand: str, series: str, conf: float, dpi: int,
           pages: str, document_id: int, ui_run_id: int) -> str:
    """카탈로그 수집 잡 실행 → dagster run_id 반환.

    document_id/ui_run_id 를 함께 넘겨야 수집 결과가 어느 문서·어느 런의 것인지 DB 에 연결된다.
    """
    run_config = {
        "ops": {
            "catalog_pdf_images": {
                "config": {
                    "pdf_url": pdf_url,
                    "brand": brand or "Osstem",
                    "series": series or "_unknown",
                    "conf": float(conf),
                    "dpi": int(dpi),
                    "pages": pages or "",
                    "document_id": int(document_id),
                    "ui_run_id": int(ui_run_id),
                }
            }
        }
    }
    return _client().submit_job_execution(JOB, run_config=run_config)


def status(run_id: str) -> str:
    """런 상태 문자열 (STARTED/SUCCESS/FAILURE/...)."""
    try:
        st = _client().get_run_status(run_id)
        return getattr(st, "value", str(st))
    except Exception as e:  # noqa: BLE001
        return f"UNKNOWN({e.__class__.__name__})"
