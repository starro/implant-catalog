"""Dagster Config — Launchpad 에서 입력되는 런타임 파라미터 스키마.

UI 에서 자산 Materialize 시 이 필드들이 편집 폼(YAML)으로 뜬다 → 여기에 URL 입력.
"""
from dagster import Config


class SiteXrayConfig(Config):
    """Job A: whatimplantisthat API 기반 X-ray 수집."""
    api_url: str = "https://whatimplantisthat.com/api/implants/all"
    # company_name 부분일치 필터 (예: 'Osstem' → 'Osstem Implant Company')
    company_filter: str = "Osstem"
    brand: str = "Osstem"          # declared (필터로 확정)
    modality: str = "xray"         # images[].meta radioimg → xray
    auto_approve: bool = True      # 데모: 검수 건너뛰고 training 까지 완주
    limit: int = 0                 # 0=전체, >0 이면 이미지 개수 상한 (테스트용)
    document_id: int = 0           # UI 가 만든 document.id (0 = UI 미경유 직접 실행)
    ui_run_id: int = 0             # UI 가 만든 run.id (0 = UI 미경유)


class CatalogPdfConfig(Config):
    """Job B: 카탈로그 PDF URL 기반 수집."""
    pdf_url: str                   # 입력 필수 (오스템 카탈로그 PDF URL)
    brand: str = "Osstem"          # declared (취득 시 앎)
    series: str = "_unknown"       # 미리 알면 선언 (예: 'GS') → review/<brand>/<series>/catalog/. 모르면 _unknown
    modality: str = "catalog"
    auto_approve: bool = True
    dpi: int = 150
    conf: float = 0.35
    min_image_px: int = 120
    pages: str = ""                # "" = 전체, "1,2,5" = 특정 페이지 (테스트용)
    document_id: int = 0           # UI 가 만든 document.id (0 = UI 미경유 직접 실행)
    ui_run_id: int = 0             # UI 가 만든 run.id (0 = UI 미경유)
