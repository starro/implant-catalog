"""단일 해상도 페이지 렌더 — 검출·VLM·크롭에 공통으로 쓰는 페이지 이미지 + 텍스트."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterator

from ..sources.pdf_util import parse_pages


@dataclass
class RenderedPage:
    page_no: int
    image: "object"    # PIL.Image.Image (지연 import 회피용 느슨한 타입)
    text: str


def render_pdf(pdf_path, pages: str = "", *, dpi: int = 200,
               log=print) -> Iterator[RenderedPage]:
    import fitz
    from PIL import Image

    doc = fitz.open(str(pdf_path))
    want = parse_pages(pages)
    idxs = ([n - 1 for n in want if 1 <= n <= doc.page_count]
            if want else range(doc.page_count))
    for i in idxs:
        page = doc[i]
        try:
            pix = page.get_pixmap(dpi=dpi)
            image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
            text = page.get_text()
        except Exception as e:  # noqa: BLE001 — 페이지 렌더 실패는 스킵+로그(§8)
            log(f"[render] page {i + 1} 렌더 실패 — 건너뜀 ({e})")
            continue
        yield RenderedPage(page_no=i + 1, image=image, text=text)
    doc.close()
