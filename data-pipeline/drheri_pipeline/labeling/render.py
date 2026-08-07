"""이원 해상도 페이지 렌더 — 고해상도 마스터(크롭용) + 다운스케일 뷰(검출·VLM용)."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterator

from ..sources.pdf_util import parse_pages


@dataclass
class RenderedPage:
    page_no: int
    master: "object"   # PIL.Image.Image (지연 import 회피용 느슨한 타입)
    view: "object"
    scale: float
    text: str


def render_pdf(pdf_path, pages: str = "", *, master_dpi: int = 300,
               view_long_px: int = 1024, log=print) -> Iterator[RenderedPage]:
    import fitz
    from PIL import Image

    doc = fitz.open(str(pdf_path))
    want = parse_pages(pages)
    idxs = ([n - 1 for n in want if 1 <= n <= doc.page_count]
            if want else range(doc.page_count))
    for i in idxs:
        page = doc[i]
        pix = page.get_pixmap(dpi=master_dpi)
        master = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
        long_side = max(master.size)
        ratio = view_long_px / long_side
        view = master.resize((max(1, round(master.width * ratio)),
                              max(1, round(master.height * ratio))))
        scale = master.width / view.width
        yield RenderedPage(page_no=i + 1, master=master, view=view,
                           scale=scale, text=page.get_text())
    doc.close()
