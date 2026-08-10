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


def render_pdf(pdf_path, pages: str = "", *, dpi: int = 200,
               log=print) -> Iterator[RenderedPage]:
    import fitz
    from PIL import Image

    data, _ = fetch_pdf_bytes(str(pdf_path), log)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        want = parse_pages(pages)
        idxs = ([n - 1 for n in want if 1 <= n <= doc.page_count]
                if want else range(doc.page_count))
        for i in idxs:
            page = doc[i]
            try:
                pix = page.get_pixmap(dpi=dpi)
                image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
                text = page.get_text()
                sc = dpi / 72.0                    # PDF point → 렌더 픽셀
                words = [(w[0] * sc, w[1] * sc, w[2] * sc, w[3] * sc, w[4])
                         for w in page.get_text("words")]
            except Exception as e:  # noqa: BLE001 — 페이지 렌더 실패는 스킵+로그(§8)
                log(f"[render] page {i + 1} 렌더 실패 — 건너뜀 ({e})")
                continue
            yield RenderedPage(page_no=i + 1, image=image, text=text, words=words)
    finally:
        doc.close()
