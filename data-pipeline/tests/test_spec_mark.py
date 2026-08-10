from drheri_pipeline.labeling import spec_mark
from drheri_pipeline.labeling.spec_mark import MarkSpec, spec_for_boxes, _parse


class _B:
    def __init__(self, x):
        self.xyxy = (x, x, x + 1, x + 1)
        self.tag = x


def test_parse_normalizes_units():
    j = _parse('{"is_fixture": true, "diameter": "F 6.0", "length": "10mm", "code": "ET3R6010B", "confidence": 0.8}')
    assert j.diameter == "6.0" and j.length == "10" and j.part_number == "ET3R6010B"


def test_spec_for_boxes_preserves_order_parallel(monkeypatch):
    monkeypatch.setattr(spec_mark, "mark_page", lambda img, boxes: boxes[0])
    monkeypatch.setattr(spec_mark, "_call",
                        lambda marked, brand, url, mn: MarkSpec(True, str(marked.tag), None, None, None, 0.9))
    out = spec_for_boxes(None, [_B(0), _B(1), _B(2), _B(3)], "X", workers=3)
    assert [s.model for s in out] == ["0", "1", "2", "3"]   # 병렬이어도 입력 순서 보존


def test_spec_for_boxes_isolates_failure(monkeypatch):
    def call(marked, brand, url, mn):
        if marked.tag == 1:
            raise RuntimeError("boom")
        return MarkSpec(True, str(marked.tag), None, None, None, 0.9)
    monkeypatch.setattr(spec_mark, "mark_page", lambda img, boxes: boxes[0])
    monkeypatch.setattr(spec_mark, "_call", call)
    out = spec_for_boxes(None, [_B(0), _B(1), _B(2)], "X", workers=2)
    assert out[1].is_fixture is None and out[0].model == "0" and out[2].model == "2"
