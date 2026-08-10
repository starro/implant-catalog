"""PDF 텍스트 좌표로 렌더↔직경 기하 매칭.

VLM(8B)이 못 하는 공간 grounding — "각 렌더는 자기 직경그룹과 같은 높이에 배치" — 을
결정적으로 푼다. PyMuPDF `get_text("words")` 의 단어 bbox(픽셀좌표로 스케일된 것)를 받아,
직경 후보 토큰들의 y-범위를 직경값별 밴드로 묶고, 각 박스 y중심이 든 밴드를 배정한다.

텍스트 레이어가 없거나(스캔 PDF) 직경 토큰이 안 잡히면 None 을 돌려 VLM 값으로 폴백한다
→ 레이아웃/문서형식 무관(신호 있을 때만 기하 우선)."""
from __future__ import annotations

import re
from collections import defaultdict

# 임플란트 직경으로 그럴듯한 소수 토큰(3.25, 4.1, 5.5 …). 길이(L8.5)는 'L' 접두라 매칭 안 됨.
_DIA = re.compile(r"^\d\.\d{1,2}$")


def _diameter_words(words) -> list[tuple[str, float]]:
    """직경 후보 = 2.8~8.0 소수 토큰 중 페이지에서 2회 이상 반복되는 값.

    (직경은 길이 개수만큼 반복 등장, 일회성 숫자는 배제) → (값, y중심) 리스트.
    하한 2.8: Hex 연결부 사이즈(1.2/2.1/2.5)를 임플란트 직경으로 오인하지 않게(임플란트는 ≥3.0)."""
    counts: dict[str, int] = defaultdict(int)
    cand: list[tuple[str, float]] = []
    for w in words:
        t = str(w[4]).strip()
        if _DIA.match(t) and 2.8 <= float(t) <= 8.0:
            counts[t] += 1
            cand.append((t, (float(w[1]) + float(w[3])) / 2))
    return [(t, yc) for (t, yc) in cand if counts[t] >= 2]


def diameter_for_boxes(words, boxes) -> list[str | None]:
    """각 박스의 y중심이 속한 직경 밴드를 배정. 신호 없으면 전부 None(→ VLM 폴백).

    words: (x0,y0,x1,y1,text,...) 픽셀좌표 시퀀스.  boxes: .xyxy(px) 를 가진 객체들."""
    diams = _diameter_words(words)
    if not diams:
        return [None] * len(boxes)
    band: dict[str, tuple[float, float]] = {}      # 직경값 → (y_min, y_max)
    for t, yc in diams:
        lo, hi = band.get(t, (yc, yc))
        band[t] = (min(lo, yc), max(hi, yc))
    out: list[str | None] = []
    for b in boxes:
        by = (b.xyxy[1] + b.xyxy[3]) / 2
        inside = [(t, lo, hi) for t, (lo, hi) in band.items() if lo - 5 <= by <= hi + 5]
        if inside:                                 # 포함 밴드 중 밴드중심 최근접
            out.append(min(inside, key=lambda c: abs((c[1] + c[2]) / 2 - by))[0])
        else:                                      # 포함 없으면 전체 밴드중심 최근접
            out.append(min(band.items(),
                           key=lambda kv: abs((kv[1][0] + kv[1][1]) / 2 - by))[0])
    return out
