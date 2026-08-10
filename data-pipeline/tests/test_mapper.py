import json
from PIL import Image
from drheri_pipeline.labeling import mapper
from drheri_pipeline.labeling.detect import Box


def _resp(payload):
    class R:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return R()


def test_map_specs_single_call_happy(monkeypatch):
    calls = {"n": 0}
    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return _resp([{"index": 0, "model": "SC", "diameter": "4.1", "length": None,
                       "part_number": "58160", "confidence": 0.9, "evidence": "SC 4.1"}])
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    specs = mapper.map_specs(view, master, [Box(0.5, (1, 1, 5, 5))], "BEGO", "REF 58160")
    assert calls["n"] == 1
    assert specs[0].model == "SC" and specs[0].diameter == "4.1" and specs[0].index == 0


def test_map_specs_partial_batch_fills_missing_no_extra_calls(monkeypatch):
    # 2박스인데 배치가 1행만 반환 → 개별콜 없이(1콜) 채우고, 빠진 박스는 null
    calls = {"n": 0}
    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return _resp([{"index": 0, "model": "A", "diameter": "4.1", "confidence": 0.8}])
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    boxes = [Box(0.5, (1, 1, 5, 5)), Box(0.5, (6, 6, 9, 9))]
    specs = mapper.map_specs(view, master, boxes, "BEGO", "txt")
    assert calls["n"] == 1                         # 크롭 개별콜(fallback) 안 함
    assert len(specs) == 2
    assert specs[0].model == "A" and specs[1].model is None and specs[1].confidence == 0.0


def test_map_specs_normalizes_1based_index(monkeypatch):
    # VLM 이 1-based index(1,2)로 주면 0-base(0,1)로 보정해 정렬
    def fake_post(url, json=None, timeout=None):
        return _resp([{"index": 1, "model": "A", "diameter": "3.25", "confidence": 0.9},
                      {"index": 2, "model": "B", "diameter": "4.1", "confidence": 0.9}])
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    boxes = [Box(0.5, (1, 1, 5, 5)), Box(0.5, (6, 6, 9, 9))]
    specs = mapper.map_specs(view, master, boxes, "BEGO", "txt")
    assert [s.model for s in specs] == ["A", "B"] and [s.index for s in specs] == [0, 1]


def test_map_specs_parses_is_fixture(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _resp([{"index": 0, "is_fixture": True, "model": "SC", "diameter": "4.1", "confidence": 0.9},
                      {"index": 1, "is_fixture": False, "confidence": 0.2}])
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    boxes = [Box(0.5, (1, 1, 5, 5)), Box(0.5, (6, 6, 9, 9))]
    specs = mapper.map_specs(view, master, boxes, "BEGO", "txt")
    assert specs[0].is_fixture is True and specs[1].is_fixture is False


def test_map_specs_null_confidence_does_not_crash(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _resp([{"index": 0, "model": "SC", "diameter": "4.1", "confidence": None}])
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    specs = mapper.map_specs(view, master, [Box(0.5, (1, 1, 5, 5))], "BEGO", "txt")
    assert len(specs) == 1 and specs[0].confidence == 0.0 and specs[0].model == "SC"
