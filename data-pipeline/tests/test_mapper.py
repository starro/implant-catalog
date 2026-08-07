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


def test_map_specs_count_mismatch_falls_back_to_per_box(monkeypatch):
    # 1콜이 2박스인데 1개만 반환 → 박스별 개별콜(2회) fallback
    seq = [
        _resp([{"index": 0, "model": "A", "diameter": "4.1", "confidence": 0.8}]),  # mismatch
        _resp([{"index": 0, "model": "A", "diameter": "4.1", "confidence": 0.8}]),  # per-box 0
        _resp([{"index": 0, "model": "B", "diameter": "5.0", "confidence": 0.7}]),  # per-box 1
    ]
    def fake_post(url, json=None, timeout=None): return seq.pop(0)
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    boxes = [Box(0.5, (1, 1, 5, 5)), Box(0.5, (6, 6, 9, 9))]
    specs = mapper.map_specs(view, master, boxes, "BEGO", "txt")
    assert [s.model for s in specs] == ["A", "B"] and len(specs) == 2
