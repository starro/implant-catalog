from drheri_pipeline.labeling.heading_model import model_from_heading


def test_strips_suffix_and_keeps_series():
    assert model_from_heading("ETIII NH Implant") == "ETIII NH"


def test_strips_brand():
    assert model_from_heading("Hiossen ETIII System", brand="Hiossen") == "ETIII"


def test_empty_or_none():
    assert model_from_heading("") is None
    assert model_from_heading(None) is None


def test_only_stopwords_returns_none():
    assert model_from_heading("Implant System") is None


def test_too_long_returns_none():
    # 문장 수준 제목 오인 방지
    assert model_from_heading("Recommended implant placement torque is 40 Ncm or less") is None
