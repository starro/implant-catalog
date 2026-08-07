"""Job B — 카탈로그 PDF URL 기반 수집.

URL 다운로드 → raw/<brand>/<source>/<file>.pdf → DocLayout-YOLO 로 figure 검출·crop
→ review/<brand>/_unknown/_unknown/catalog/<hash>. (series/model 은 검수에서 채움)

PoC(image-origin-poc/layout_ingest.py) 에서 검증된 추출 로직 이식.
무거운 의존성(fitz, doclayout_yolo)은 지연 import — Dagster 로드 시점엔 불필요.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .. import storage

_UA = {"User-Agent": "Mozilla/5.0"}
_MODEL = None  # 프로세스당 1회 로드

# Osstem 시리즈 패턴 — 페이지 전체 텍스트에서 단일 시리즈면 그 페이지 figure 에 자동 부여.
# (긴 토큰 먼저 매칭되도록 정렬: TSIII 가 TSII 보다 앞)
_SERIES_RE = re.compile(r"\b(TSIV|TSIII|TSII|SSIII|SSII|GSIII|GSII|USIV|USIII|USII|MS)\b")


def _page_series(page_text: str) -> str | None:
    """페이지 전체 텍스트에 시리즈가 '딱 하나'면 그 시리즈, 아니면 None(애매/없음)."""
    found = set(_SERIES_RE.findall(page_text or ""))
    return next(iter(found)) if len(found) == 1 else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_model():
    global _MODEL
    if _MODEL is None:
        from huggingface_hub import hf_hub_download
        from doclayout_yolo import YOLOv10
        path = hf_hub_download(
            repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
            filename="doclayout_yolo_docstructbench_imgsz1024.pt",
        )
        _MODEL = YOLOv10(path)
    return _MODEL


def _fetch_pdf_bytes(url: str, log) -> tuple[bytes, str]:
    """http(s) URL · file:// · 로컬 경로 모두 지원 → (bytes, 파일명)."""
    local = Path(url)
    if local.exists():                       # 로컬 경로 직접 (local_upload)
        log(f"[catalog_pdf] local file {url}")
        return local.read_bytes(), local.name
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        log(f"[catalog_pdf] download {url}")
        resp = httpx.get(url, headers=_UA, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        return resp.content, (Path(parsed.path).name or "catalog.pdf")
    if parsed.scheme == "file":
        from urllib.request import url2pathname
        fp = Path(url2pathname(parsed.path))
        return fp.read_bytes(), fp.name
    raise ValueError(f"지원하지 않는 PDF 경로: {url}")


def _download_pdf(url: str, brand: str, log) -> Path:
    data, name = _fetch_pdf_bytes(url, log)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    dst = storage.raw_path(brand, "catalog_pdf", name)
    dst.write_bytes(data)
    log(f"[catalog_pdf] raw 저장 → {storage.rel(dst)}")
    return dst


def _parse_pages(pages: str) -> list[int] | None:
    """페이지 지정 파싱. '' → None(전체), '12' → [12], '12-16' → [12..16],
    '40-42, 12-14, 13' → 정렬·중복제거된 [12,13,14,40,41,42].

    잘못된 입력(숫자 아님/하한>상한/0 이하/형식 불량)은 ValueError 로 막아
    수집이 조용히 깨지지 않게 한다.
    """
    pages = (pages or "").strip()
    if not pages:
        return None
    result: set[int] = set()
    for token in pages.replace(" ", "").split(","):
        if not token:
            continue
        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(f"잘못된 페이지 범위: '{token}' (예: 12-26)")
            lo, hi = int(parts[0]), int(parts[1])   # int() 가 비숫자면 ValueError
            if lo < 1 or hi < 1:
                raise ValueError(f"페이지는 1 이상이어야 합니다: '{token}'")
            if lo > hi:
                raise ValueError(f"범위 시작이 끝보다 큽니다: '{token}' (예: 12-26)")
            result.update(range(lo, hi + 1))
        else:
            n = int(token)                          # 비숫자면 ValueError
            if n < 1:
                raise ValueError(f"페이지는 1 이상이어야 합니다: '{token}'")
            result.add(n)
    return sorted(result)


def ingest(config, log=print) -> list[dict]:
    """PDF 다운로드 → figure 추출 → review/ 저장 → 매니페스트 레코드 반환."""
    import fitz
    from PIL import Image

    pdf_path = _download_pdf(config.pdf_url, config.brand, log)
    model = _get_model()
    doc = fitz.open(str(pdf_path))

    want = _parse_pages(config.pages)
    if want:
        idxs = sorted({n - 1 for n in want if 1 <= n <= doc.page_count})
    else:
        idxs = range(doc.page_count)

    sc = 72.0 / config.dpi   # 렌더 px → PDF point
    pad = 40
    out: list[dict] = []
    seen: set[str] = set()
    for page_index in idxs:
        page = doc[page_index]
        # 검출만 — 확정 series 는 config(기본 _unknown, 사람이 라벨). 페이지감지는 '제안 힌트'로만.
        pg_series = _page_series(page.get_text())
        series_final = config.series                                   # 자동 확정 안 함 (오염 방지)
        suggested = pg_series if config.series == "_unknown" else None  # 사람에게 보여줄 힌트
        pix = page.get_pixmap(dpi=config.dpi)
        page_img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
        det = model.predict(page_img, imgsz=1024, conf=config.conf, device="cpu", verbose=False)[0]
        names = det.names
        for b in det.boxes:
            cls = names[int(b.cls)]
            if not any(k in cls.lower() for k in ("figure", "picture", "image")):
                continue
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            w, h = x2 - x1, y2 - y1
            if w < config.min_image_px or h < config.min_image_px:
                continue
            crop = page_img.crop((x1, y1, x2, y2))
            trect = fitz.Rect((x1 - pad) * sc, (y1 - pad) * sc, (x2 + pad) * sc, (y2 + pad) * sc)
            nearby = page.get_textbox(trect).strip()
            buf = BytesIO()
            crop.save(buf, "PNG")
            png = buf.getvalue()
            chash = hashlib.sha256(png).hexdigest()
            if chash in seen:
                continue
            seen.add(chash)
            dst = storage.stage_image_path("review", config.brand, series_final, "_unknown",
                                           config.modality, chash, "png")
            if not dst.exists():
                dst.write_bytes(png)
            out.append({
                "content_hash": chash,
                "path": storage.rel(dst),
                "stage": "review",
                "status": "review",
                "brand": config.brand,
                "series": series_final,
                "surface": None,                     # SA/CA/SOI/RBM... 사람이 라벨 (export 시 series 와 합성)
                "suggested_series": suggested,       # 페이지텍스트 기반 제안 (확정 아님, 사람 검토용)
                "page_series": pg_series,
                "series_resolution": "config" if config.series != "_unknown" else "suggest",
                "model": "_unknown",
                "modality": config.modality,
                "source_id": "catalog_pdf",
                "source_type": "url_pdf",
                "origin_url": f"{config.pdf_url}#page={page_index + 1}",
                "page_no": page_index + 1,
                "bbox": [x1, y1, x2, y2],
                "px": f"{w}x{h}",
                "dpi": config.dpi,
                "det_conf": round(float(b.conf), 3),
                "nearby_text": nearby[:500],
                "brand_resolution": "declared",
                "fetched_at": _now(),
            })
    log(f"[catalog_pdf] review figures {len(out)}장 (pages={len(list(idxs))})")
    return out
