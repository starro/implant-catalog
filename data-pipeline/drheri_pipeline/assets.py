"""Dagster 자산 + 잡 — 두 수집 경로(site_xray / catalog_pdf).

각 자산: 소스 수집 → review 저장 → SQLite 기록 → FiftyOne 등록.
URL 등 파라미터는 Config(=UI 또는 Launchpad 입력)로 받는다.

주의: 이 모듈은 `from __future__ import annotations` 를 쓰지 않는다 —
그게 `config: SiteXrayConfig` 를 문자열 annotation 으로 만들어 Dagster Config 해석이 실패한다.
"""
from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset, define_asset_job

from . import review, storage
from .config import CatalogPdfConfig, SiteXrayConfig
from .db import conn as db_conn
from .db import writes as db_writes
from .sources import catalog_pdf, site_xray


def record_ingest(records: list, document_id: int, ui_run_id: int) -> int:
    """수집 결과를 운영 DB(image + image_origin)에 기록. document_id 가 0이면 건너뛴다.

    ui_run_id 가 있으면 같은 트랜잭션에서 run.extracted 도 갱신한다 — 훅(sensors.hook_payload)은
    실제 추출 개수를 모르고 항상 0을 보내므로, "추출" 수의 진짜 출처는 여기뿐이다.
    """
    if not records or not document_id:
        return 0
    db_conn.migrate()
    with db_conn.session() as cx:
        for r in records:
            db_writes.record_image(cx, r, document_id, ui_run_id or None)
        if ui_run_id:
            cx.execute("UPDATE run SET extracted=? WHERE id=?", (len(records), ui_run_id))
    return len(records)


@asset(group_name="ingest", description="whatimplantisthat API 기반 Osstem X-ray 수집 → review")
def site_xray_images(context: AssetExecutionContext, config: SiteXrayConfig) -> MaterializeResult:
    records = site_xray.ingest(config, log=context.log.info)
    storage.append_manifest(records)                 # 롤백 대비 로그 (진실의 원천은 DB)
    recorded = record_ingest(records, config.document_id, config.ui_run_id)
    review.register_fiftyone(records, log=context.log.info)
    return MaterializeResult(metadata={
        "review_count": len(records),
        "recorded_count": recorded,
        "brand": config.brand,
        "modality": config.modality,
        "sample_paths": MetadataValue.json([r["path"] for r in records[:5]]),
    })


@asset(group_name="ingest", description="카탈로그 PDF URL → DocLayout 추출 → review")
def catalog_pdf_images(context: AssetExecutionContext, config: CatalogPdfConfig) -> MaterializeResult:
    records = catalog_pdf.ingest(config, log=context.log.info)
    storage.append_manifest(records)                 # 롤백 대비 로그 (진실의 원천은 DB)
    recorded = record_ingest(records, config.document_id, config.ui_run_id)
    review.register_fiftyone(records, log=context.log.info)
    return MaterializeResult(metadata={
        "review_count": len(records),
        "recorded_count": recorded,
        "brand": config.brand,
        "pdf_url": config.pdf_url,
        "sample_paths": MetadataValue.json([r["path"] for r in records[:5]]),
    })


ingest_site_xray_job = define_asset_job("ingest_site_xray", selection=["site_xray_images"])
ingest_catalog_pdf_job = define_asset_job("ingest_catalog_pdf", selection=["catalog_pdf_images"])
