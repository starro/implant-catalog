from drheri_pipeline.labeling.crop_judge import _parse, FixtureJudge


def test_parse_true():
    j = _parse('here: {"is_fixture": true, "confidence": 0.9} done')
    assert j.is_fixture is True and j.confidence == 0.9


def test_parse_false_string_bool():
    j = _parse('{"is_fixture": "no", "confidence": 0.3}')
    assert j.is_fixture is False and j.confidence == 0.3


def test_parse_no_json_is_none():
    j = _parse("sorry I cannot tell")
    assert j.is_fixture is None and j.confidence == 0.0


def test_parse_bad_json_is_none():
    j = _parse('{"is_fixture": tru')
    assert isinstance(j, FixtureJudge) and j.is_fixture is None
