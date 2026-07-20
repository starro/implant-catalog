"""Dagster 진입점 (pyproject [tool.dagster] module_name)."""
from dagster import Definitions

from . import assets, sensors

defs = Definitions(
    assets=[assets.site_xray_images, assets.catalog_pdf_images],
    jobs=[assets.ingest_site_xray_job, assets.ingest_catalog_pdf_job],
    sensors=[sensors.on_run_success, sensors.on_run_failure],
)
