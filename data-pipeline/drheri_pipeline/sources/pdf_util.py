"""PDF 입력 공용 유틸 — 페이지 지정 파싱 + URL/파일 바이트 취득.

catalog_pdf(구 DocLayout 경로)와 labeling(신 GDINO+VLM 경로)이 공유한다.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

_UA = {"User-Agent": "Mozilla/5.0"}


def parse_pages(pages: str) -> list[int] | None:
    """'' → None(전체), '12' → [12], '12-16' → [12..16], 정렬·중복제거. 불량 입력은 ValueError."""
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
            lo, hi = int(parts[0]), int(parts[1])
            if lo < 1 or hi < 1:
                raise ValueError(f"페이지는 1 이상이어야 합니다: '{token}'")
            if lo > hi:
                raise ValueError(f"범위 시작이 끝보다 큽니다: '{token}' (예: 12-26)")
            result.update(range(lo, hi + 1))
        else:
            n = int(token)
            if n < 1:
                raise ValueError(f"페이지는 1 이상이어야 합니다: '{token}'")
            result.add(n)
    return sorted(result)


def fetch_pdf_bytes(url: str, log=print) -> tuple[bytes, str]:
    """http(s) URL · file:// · 로컬 경로 모두 지원 → (bytes, 파일명)."""
    local = Path(url)
    if local.exists():
        log(f"[pdf_util] local file {url}")
        return local.read_bytes(), local.name
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        log(f"[pdf_util] download {url}")
        resp = httpx.get(url, headers=_UA, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        return resp.content, (Path(parsed.path).name or "catalog.pdf")
    if parsed.scheme == "file":
        from urllib.request import url2pathname
        fp = Path(url2pathname(parsed.path))
        return fp.read_bytes(), fp.name
    raise ValueError(f"지원하지 않는 PDF 경로: {url}")
