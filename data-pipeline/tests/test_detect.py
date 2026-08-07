from PIL import Image
from drheri_pipeline.labeling import detect


def test_to_master_scales_coords():
    b = detect.Box(score=0.5, xyxy=(10, 20, 30, 40))
    m = detect.to_master(b, scale=2.0)
    assert m.xyxy == (20, 40, 60, 80) and m.score == 0.5


def test_detect_fixtures_parses_service_response(monkeypatch):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"boxes": [{"score": 0.52, "xyxy": [1, 2, 3, 4]}]}

    def fake_post(url, json=None, timeout=None):
        assert json["prompt"] == "a gray implant object"
        return Resp()

    monkeypatch.setattr(detect.httpx, "post", fake_post)
    boxes = detect.detect_fixtures(Image.new("RGB", (8, 8)))
    assert len(boxes) == 1 and boxes[0].xyxy == (1, 2, 3, 4) and boxes[0].score == 0.52
