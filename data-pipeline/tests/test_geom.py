from drheri_pipeline.labeling import geom


class _B:
    def __init__(self, xyxy):
        self.xyxy = xyxy


def _w(x0, y0, x1, y1, t):
    return (x0, y0, x1, y1, t)


def test_diameter_for_boxes_bands():
    # 3.25 그룹 y 100~200, 4.5 그룹 y 300~400 (각 3회 반복). L8.5 는 길이(L접두)라 무시.
    words = [
        _w(50, 100, 80, 115, "3.25"), _w(50, 150, 80, 165, "3.25"), _w(50, 200, 80, 215, "3.25"),
        _w(50, 300, 80, 315, "4.5"), _w(50, 350, 80, 365, "4.5"), _w(50, 400, 80, 415, "4.5"),
        _w(120, 100, 160, 115, "L8.5"),
    ]
    boxes = [_B((400, 120, 450, 180)), _B((400, 320, 450, 380))]   # y중심 150, 350
    assert geom.diameter_for_boxes(words, boxes) == ["3.25", "4.5"]


def test_none_when_no_diameter_tokens():
    words = [_w(0, 0, 10, 10, "REF"), _w(0, 20, 10, 30, "58160")]
    assert geom.diameter_for_boxes(words, [_B((0, 0, 5, 5))]) == [None]


def test_ignores_singleton_number():
    # 한 번만 등장하는 4.1 은 직경 밴드로 안 봄(반복>=2 규칙) → None (VLM 폴백)
    assert geom.diameter_for_boxes([_w(0, 0, 10, 10, "4.1")], [_B((0, 0, 5, 5))]) == [None]
