from drheri_pipeline.labeling import partnum


def test_parse_length_generic_mm_token():
    # 흔한 포맷: 끝의 두 자리쌍이 직경·길이 (예: BEGO 58xxx 는 표에서 length 별도)
    assert partnum.parse_length("BEGO", "S 4.1 x 11.5") == "11.5"
    assert partnum.parse_length("Osstem", "L=10mm") == "10"


def test_parse_length_none_when_absent():
    assert partnum.parse_length("BEGO", None) is None
    assert partnum.parse_length("BEGO", "58160") is None   # 순수 REF 코드엔 길이 없음


def test_parse_length_picks_plausible_range():
    # 6~20mm 범위만 length 후보 (직경 3~7 과 구분)
    assert partnum.parse_length("X", "3.75 / 13") == "13"
