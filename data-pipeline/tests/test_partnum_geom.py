from drheri_pipeline.labeling.partnum_geom import code_words, codes_for_boxes


class _B:
    def __init__(self, xyxy):
        self.xyxy = xyxy


def test_code_words_filters_non_codes():
    words = [
        (0, 0, 1, 1, "ET3R4010B"),   # 코드
        (0, 0, 1, 1, "8.5"),          # 숫자
        (0, 0, 1, 1, "Regular"),      # 단어(숫자 없음)
        (0, 0, 1, 1, "Hex"),          # 짧은 단어
        (0, 0, 1, 1, "ET3M3008B"),   # 코드
    ]
    got = [c[0] for c in code_words(words)]
    assert got == ["ET3R4010B", "ET3M3008B"]


def test_codes_assigned_to_nearest_left_box_same_row():
    # 두 컬럼(각 2행) — 코드는 자기 컬럼 박스(바로 왼쪽)에 붙어야 한다.
    boxes = [_B((100, 300, 200, 500)), _B((400, 300, 500, 500))]
    words = [
        (250, 340, 340, 360, "ET3R4007B"),   # 컬럼1 행1
        (250, 440, 340, 460, "ET3R4008B"),   # 컬럼1 행2
        (550, 340, 640, 360, "ET3R4507B"),   # 컬럼2 행1
        (550, 440, 640, 460, "ET3R4508B"),   # 컬럼2 행2
        (300, 340, 340, 360, "8.5"),          # 코드 아님(무시)
    ]
    got = codes_for_boxes(words, boxes)
    assert got[0] == ["ET3R4007B", "ET3R4008B"]     # 위→아래 정렬
    assert got[1] == ["ET3R4507B", "ET3R4508B"]


def test_no_codes_returns_empty_lists():
    boxes = [_B((100, 300, 200, 500))]
    words = [(250, 340, 340, 360, "8.5"), (300, 360, 360, 380, "Regular")]
    assert codes_for_boxes(words, boxes) == [[]]
