"""Job A — whatimplantisthat.com API 기반 X-ray 수집.

API(`/api/implants/all`)가 제조사/브랜드/이미지타입 + **이미지 URL을 직접** 제공 →
Playwright 불필요, 순수 httpx 다운로드. (raw 단계 생략, 바로 review)

레코드: company_name(제조사), name(브랜드/시리즈), images[].{url, meta, original_filename}
meta: radioimg → xray, clinicalimg → catalog
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .. import storage
from ..normalize import normalize_model, normalize_series

_META_TO_MODALITY = {"radioimg": "xray", "clinicalimg": "catalog"}
_UA = {"User-Agent": "Mozilla/5.0"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_series(name: str, brand: str) -> str:
    s = normalize_series(name)
    # 'Osstem TSII' 처럼 시리즈명이 브랜드로 시작하면 접두 제거
    if s.lower().startswith(brand.lower() + " "):
        s = s[len(brand) + 1:].strip()
    return s or "_unknown"


def ingest(config, log=print) -> list[dict]:
    """API 수집 → review/ 에 이미지 저장 → 매니페스트 레코드 리스트 반환."""
    log(f"[site_xray] fetch {config.api_url}")
    data = httpx.get(config.api_url, headers=_UA, timeout=60).json()
    records = data.get("data") if isinstance(data, dict) else data
    cf = (config.company_filter or "").lower()

    out: list[dict] = []
    seen: set[str] = set()
    for r in records or []:
        if cf and cf not in (r.get("company_name") or "").lower():
            continue
        series = _derive_series(r.get("name") or "", config.brand)
        for im in r.get("images") or []:
            modality = _META_TO_MODALITY.get((im.get("meta") or "").strip())
            if modality != config.modality:
                continue
            url = im.get("url")
            if not url:
                continue
            try:
                resp = httpx.get(url, headers=_UA, timeout=60)
                resp.raise_for_status()
            except Exception as e:  # noqa: BLE001
                log(f"[site_xray]   skip {url}: {e}")
                continue
            raw = resp.content
            h = storage.content_hash(raw)
            if h in seen:
                continue
            seen.add(h)
            ext = (Path(urlparse(url).path).suffix.lstrip(".") or "jpg").lower()
            model = normalize_model(Path(im.get("original_filename") or im.get("filename") or h).stem)
            dst = storage.stage_image_path("review", config.brand, series, model, modality, h, ext)
            if not dst.exists():
                dst.write_bytes(raw)
            out.append({
                "content_hash": h,
                "path": storage.rel(dst),
                "stage": "review",
                "status": "review",
                "brand": config.brand,
                "series": series,
                "surface": None,
                "model": model,
                "modality": modality,
                "source_id": "whatimplantisthat",
                "source_type": "url_site",
                "origin_url": url,
                "brand_resolution": "declared+structured",  # brand=필터, series/model=사이트 구조
                "fetched_at": _now(),
            })
            if config.limit and len(out) >= config.limit:
                log(f"[site_xray] limit {config.limit} 도달")
                return out
    log(f"[site_xray] review 이미지 {len(out)}장")
    return out
