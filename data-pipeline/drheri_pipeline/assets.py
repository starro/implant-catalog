"""Dagster 자산 + 잡 — 두 수집 경로(site_xray / catalog_pdf).

각 자산: 소스 수집 → review 저장 + 매니페스트 → FiftyOne 등록 → (auto_approve 면) training 승급.
URL 등 파라미터는 Config(=Launchpad 입력)로 받는다.

주의: 이 모듈은 `from __future__ import annotations` 를 쓰지 않는다 —
그게 `config: SiteXrayConfig` 를 문자열 annotation 으로 만들어 Dagster Config 해석이 실패한다.
"""
from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset, define_asset_job

from . import review, storage
from .config import CatalogPdfConfig, SiteXrayConfig
from .sources import catalog_pdf, site_xray


@asset(group_name="ingest", description="whatimplantisthat API 기반 Osstem X-ray 수집 → review(→training)")
def site_xray_images(context: AssetExecutionContext, config: SiteXrayConfig) -> MaterializeResult:
    records = site_xray.ingest(config, log=context.log.info)
    storage.append_manifest(records)
    review.register_fiftyone(records, log=context.log.info)
    promoted = 0
    if config.auto_approve:
        promoted = review.promote([r["content_hash"] for r in records], log=context.log.info)
    return MaterializeResult(metadata={
        "review_count": len(records),
        "promoted_count": promoted,
        "brand": config.brand,
        "modality": config.modality,
        "sample_paths": MetadataValue.json([r["path"] for r in records[:5]]),
    })


@asset(group_name="ingest", description="카탈로그 PDF URL → DocLayout 추출 → review(→training)")
def catalog_pdf_images(context: AssetExecutionContext, config: CatalogPdfConfig) -> MaterializeResult:
    records = catalog_pdf.ingest(config, log=context.log.info)
    storage.append_manifest(records)
    review.register_fiftyone(records, log=context.log.info)
    promoted = 0
    if config.auto_approve:
        promoted = review.promote([r["content_hash"] for r in records], log=context.log.info)
    return MaterializeResult(metadata={
        "review_count": len(records),
        "promoted_count": promoted,
        "brand": config.brand,
        "pdf_url": config.pdf_url,
        "sample_paths": MetadataValue.json([r["path"] for r in records[:5]]),
    })


ingest_site_xray_job = define_asset_job("ingest_site_xray", selection=["site_xray_images"])
ingest_catalog_pdf_job = define_asset_job("ingest_catalog_pdf", selection=["catalog_pdf_images"])
