import pytest
from drheri_pipeline.sources import pdf_util


def test_parse_pages_ranges_and_dedup():
    assert pdf_util.parse_pages("40-42, 12-14, 13") == [12, 13, 14, 40, 41, 42]
    assert pdf_util.parse_pages("") is None
    assert pdf_util.parse_pages("12") == [12]


def test_parse_pages_rejects_bad_input():
    with pytest.raises(ValueError):
        pdf_util.parse_pages("12-")
    with pytest.raises(ValueError):
        pdf_util.parse_pages("0")


def test_fetch_pdf_bytes_local_file(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    data, name = pdf_util.fetch_pdf_bytes(str(f))
    assert data == b"%PDF-1.4 test" and name == "a.pdf"


def test_catalog_pdf_still_exposes_private_aliases():
    # 기존 호출부/테스트 호환: catalog_pdf 가 여전히 같은 동작을 노출한다.
    from drheri_pipeline.sources import catalog_pdf
    assert catalog_pdf._parse_pages("1,2") == [1, 2]
