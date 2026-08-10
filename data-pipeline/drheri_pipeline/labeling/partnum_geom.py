"""PDF 텍스트 좌표로 박스↔주문코드(part_number) 매칭 — geom.py 의 짝.

카탈로그 표의 주문코드(ET3R4010B 등)는 '기계가 읽는 텍스트'라, 작은 글씨에 약한 8B VLM
보다 좌표 매칭이 훨씬 정확하다. geom.py 와 같은 재료(page.words, 픽셀좌표)를 재사용한다.

매칭 규칙: 각 주문코드는 '같은 행(y)에서 자기 바로 왼쪽에 있는 픽스처 박스'에 속한다
(표 레이아웃: [썸네일 | L | D | 코드]). 컬럼 박스(여러 행)는 여러 코드를 갖는다 → 리스트.
텍스트/코드가 없으면 빈 리스트 → 호출부가 VLM 값으로 폴백."""
from __future__ import annotations

import re

# 주문코드 후보: 대문자로 시작 + 글자·숫자 혼합 + 숫자 3개 이상 + 5자 이상.
# (순수 숫자·순수 단어·짧은 토큰 배제. 예: ET3R4010B ✓, Regular ✗, 8.5 ✗)
_CODE = re.compile(r"^[A-Z][A-Za-z0-9]{4,}$")


def _is_code(t: str) -> bool:
    return (bool(_CODE.match(t)) and sum(c.isdigit() for c in t) >= 3
            and any(c.isalpha() for c in t))


def code_words(words) -> list[tuple[str, float, float]]:
    """주문코드 토큰 → (코드, y중심, x0) 리스트."""
    out = []
    for w in words:
        t = str(w[4]).strip()
        if _is_code(t):
            out.append((t, (float(w[1]) + float(w[3])) / 2, float(w[0])))
    return out


def codes_for_boxes(words, boxes) -> list[list[str]]:
    """각 박스에 '같은 행에서 바로 왼쪽 박스'인 주문코드들을 배정(위→아래 정렬).

    words: (x0,y0,x1,y1,text,...) 픽셀좌표 시퀀스.  boxes: .xyxy(px) 를 가진 객체들.
    코드는 박스 y범위 안 + 박스 오른쪽(같은 셀그룹, ~박스폭 4배 이내)에 있어야 한다."""
    codes = code_words(words)
    result: list[list[tuple[float, str]]] = [[] for _ in boxes]
    for t, yc, cx in codes:
        best_i, best_dx = None, None
        for i, b in enumerate(boxes):
            x0, y0, x1, y1 = b.xyxy
            if y0 - 3 <= yc <= y1 + 3 and x1 <= cx <= x1 + (x1 - x0) * 4 + 20:
                dx = cx - x1
                if best_dx is None or dx < best_dx:
                    best_i, best_dx = i, dx
        if best_i is not None:
            result[best_i].append((yc, t))
    return [[t for _, t in sorted(lst)] for lst in result]
