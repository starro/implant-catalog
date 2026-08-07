import fitz
from drheri_pipeline.labeling import render


def _make_pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=595, height=842)  # A4 pt
        pg.insert_text((72, 72), f"REF 58160 page {i+1}")
    doc.save(str(path)); doc.close()


def test_render_pdf_dual_resolution(tmp_path):
    pdf = tmp_path / "c.pdf"; _make_pdf(pdf, pages=2)
    out = list(render.render_pdf(str(pdf), master_dpi=300, view_long_px=512))
    assert len(out) == 2
    p = out[0]
    assert p.page_no == 1
    assert max(p.view.size) == 512                 # 뷰 긴 변 고정
    assert p.master.width > p.view.width           # 마스터가 더 큼
    assert abs(p.scale - p.master.width / p.view.width) < 1e-6
    assert "REF 58160" in p.text                   # 페이지 텍스트 추출


def test_render_pdf_page_filter(tmp_path):
    pdf = tmp_path / "c.pdf"; _make_pdf(pdf, pages=3)
    out = list(render.render_pdf(str(pdf), pages="2"))
    assert [p.page_no for p in out] == [2]
