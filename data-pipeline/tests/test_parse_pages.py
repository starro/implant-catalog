import pytest

from drheri_pipeline.sources.catalog_pdf import _parse_pages


def test_empty_means_all():
    assert _parse_pages("") is None
    assert _parse_pages("   ") is None
    assert _parse_pages(None) is None


def test_single_and_list():
    assert _parse_pages("12") == [12]
    assert _parse_pages("12,13,20") == [12, 13, 20]


def test_range():
    assert _parse_pages("12-16") == [12, 13, 14, 15, 16]


def test_mixed_sorted_deduped():
    # 범위+단일 혼합, 정렬, 중복 제거
    assert _parse_pages("40-42, 12-14, 13, 41") == [12, 13, 14, 40, 41, 42]


def test_whitespace_tolerant():
    assert _parse_pages(" 12 - 14 , 20 ") == [12, 13, 14, 20]


@pytest.mark.parametrize("bad", ["abc", "12-", "-5", "1-2-3", "12,x", "0", "0-3", "26-12", "5-5-"])
def test_invalid_raises(bad):
    with pytest.raises(ValueError):
        _parse_pages(bad)
