"""단일 해상도 페이지 렌더 — 검출·VLM·크롭에 공통으로 쓰는 페이지 이미지 + 텍스트."""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Iterator

from ..sources.pdf_util import fetch_pdf_bytes, parse_pages


@dataclass
class RenderedPage:
    page_no: int
    image: "object"    # PIL.Image.Image (지연 import 회피용 느슨한 타입)
    text: str
    words: list = field(default_factory=list)   # (x0,y0,x1,y1,text) 픽셀좌표 — 기하 매칭용
    heading: str = ""   # 상단 최대폰트 제목(모델/시리즈 추출용). 큰 제목이 여러 개면 "" (모호)
    pdf_data: bytes = b""   # 원본 PDF 바이트(공유 참조) — 크롭을 고DPI 로 재렌더할 때 사용
    dpi: int = 200          # image/words 의 렌더 DPI — 크롭 좌표(픽셀→포인트) 환산 기준


def _page_heading(page) -> str:
    """상단 절반에서 '가장 큰 폰트'의 제목 1줄을 뽑는다 — 모델/시리즈 텍스트 추출용.

    한 페이지에 큰 제목(=시리즈)이 둘 이상이면 어느 걸 붙일지 모호하므로 "" 를 준다
    (→ 모델 비움, '빈칸 > 틀린값'). 한 줄의 여러 span 은 합쳐 하나의 제목으로 본다."""
    try:
        d = page.get_text("dict")
        ph = float(page.rect.height) or 1.0
    except Exception:   # noqa: BLE001
        return ""
    lines: list[tuple[float, str]] = []
    for blk in d.get("blocks", []):
        for ln in blk.get("lines", []):
            spans = [s for s in ln.get("spans", []) if str(s.get("text", "")).strip()]
            if not spans:
                continue
            if float(spans[0].get("bbox", [0, 0, 0, 0])[1]) > ph * 0.5:
                continue    # 상단 절반만
            size = max(float(s.get("size", 0.0)) for s in spans)
            txt = " ".join(str(s.get("text", "")).strip() for s in spans).strip()
            lines.append((size, txt))
    if not lines:
        return ""
    mx = max(s for s, _ in lines)
    top = list(dict.fromkeys(t for s, t in lines if s >= mx * 0.92))   # 최대폰트 ~동급 줄들
    return top[0] if len(top) == 1 else ""


def render_pdf(pdf_path, pages: str = "", *, dpi: int = 200,
               log=print, on_progress=None) -> Iterator[RenderedPage]:
    """페이지를 순서대로 렌더링해 yield. on_progress(rendered, total) 이 있으면 렌더 진행을 보고한다."""
    import fitz
    from PIL import Image

    data, _ = fetch_pdf_bytes(str(pdf_path), log)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        want = parse_pages(pages)
        idxs = list([n - 1 for n in want if 1 <= n <= doc.page_count]
                    if want else range(doc.page_count))
        total = len(idxs)
        rendered = 0
        for i in idxs:
            page = doc[i]
            try:
                pix = page.get_pixmap(dpi=dpi)
                image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
                text = page.get_text()
                sc = dpi / 72.0                    # PDF point → 렌더 픽셀
                words = [(w[0] * sc, w[1] * sc, w[2] * sc, w[3] * sc, w[4])
                         for w in page.get_text("words")]
                heading = _page_heading(page)
            except Exception as e:  # noqa: BLE001 — 페이지 렌더 실패는 스킵+로그(§8)
                log(f"[render] page {i + 1} 렌더 실패 — 건너뜀 ({e})")
                continue
            rendered += 1
            if on_progress:
                on_progress(rendered, total)
            yield RenderedPage(page_no=i + 1, image=image, text=text, words=words,
                               heading=heading, pdf_data=data, dpi=dpi)
    finally:
        doc.close()
