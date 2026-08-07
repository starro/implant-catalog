import fitz
from drheri_pipeline.labeling import render


def _make_pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=595, height=842)  # A4 pt
        pg.insert_text((72, 72), f"REF 58160 page {i+1}")
    doc.save(str(path)); doc.close()


def test_render_pdf_single_image(tmp_path):
    pdf = tmp_path / "c.pdf"; _make_pdf(pdf, pages=2)
    out = list(render.render_pdf(str(pdf), dpi=200))
    assert len(out) == 2
    p = out[0]
    assert p.page_no == 1
    assert p.image.width > 0 and p.image.height > 0
    assert p.image.width > p.image.height * 0.5    # A4 세로 렌더 형상
    assert "REF 58160" in p.text                   # 페이지 텍스트 추출


def test_render_pdf_dpi_scales_image(tmp_path):
    pdf = tmp_path / "c.pdf"; _make_pdf(pdf, pages=1)
    small = list(render.render_pdf(str(pdf), dpi=100))[0]
    big = list(render.render_pdf(str(pdf), dpi=200))[0]
    assert big.image.width > small.image.width     # dpi 노브가 해상도를 키운다


def test_render_pdf_page_filter(tmp_path):
    pdf = tmp_path / "c.pdf"; _make_pdf(pdf, pages=3)
    out = list(render.render_pdf(str(pdf), pages="2"))
    assert [p.page_no for p in out] == [2]
