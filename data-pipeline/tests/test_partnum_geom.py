from drheri_pipeline.labeling.partnum_geom import code_words, codes_for_boxes, lengths_for_boxes


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


def test_length_same_row_right_single():
    # 개별 썸네일(한 행): 오른쪽 길이값 1개 → 그 값
    boxes = [_B((100, 300, 200, 340)), _B((100, 400, 200, 440))]
    words = [
        (250, 310, 290, 330, "8.5"),    # box0 행 오른쪽
        (250, 410, 290, 430, "10"),     # box1 행 오른쪽
        (250, 310, 290, 330, "Regular"),  # 길이 아님(무시)
    ]
    assert lengths_for_boxes(words, boxes) == ["8.5", "10"]


def test_length_none_when_multiple_rows():
    # 컬럼 박스(여러 행) → 여러 길이 → None(모호)
    col = [_B((100, 300, 200, 500))]
    words = [(250, 340, 290, 360, "8.5"), (250, 440, 290, 460, "10")]
    assert lengths_for_boxes(words, col) == [None]


def test_length_none_when_no_length_right():
    # 오른쪽에 길이값 없으면 None
    boxes = [_B((100, 300, 200, 340))]
    assert lengths_for_boxes([(300, 310, 340, 330, "Regular")], boxes) == [None]
