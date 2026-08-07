from PIL import Image
from drheri_pipeline.labeling import detect


def test_detect_fixtures_parses_service_response(monkeypatch):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"boxes": [{"score": 0.52, "xyxy": [1, 2, 3, 4]}]}

    def fake_post(url, json=None, timeout=None):
        assert json["prompt"] == "an implant fixture."   # 마침표 필수(리콜)
        return Resp()

    monkeypatch.setattr(detect.httpx, "post", fake_post)
    boxes = detect.detect_fixtures(Image.new("RGB", (8, 8)))
    assert len(boxes) == 1 and boxes[0].xyxy == (1, 2, 3, 4) and boxes[0].score == 0.52
