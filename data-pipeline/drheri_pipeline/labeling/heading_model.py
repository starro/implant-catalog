"""페이지 제목 → 모델/시리즈 텍스트 추출 (render._page_heading 의 짝).

개별 크롭 방식에선 VLM 이 크롭 하나만 봐서 시리즈(페이지 제목 'ETIII NH Implant')를
못 읽는다. 시리즈는 페이지 제목이라 '읽기는 텍스트로' 원칙대로 여기서 뽑는다.
제목에서 흔한 접미사(Implant/System 등)와 브랜드명을 걷어내 시리즈만 남긴다.
모호하거나(제목 여러 개 → heading="") 너무 길면 None → 사람이 라벨('빈칸 > 틀린값')."""
from __future__ import annotations

# 시리즈가 아닌 흔한 제목 단어 — 걷어낸다.
_STOP = {"implant", "implants", "system", "systems", "fixture", "fixtures",
         "catalog", "catalogue", "dental", "line", "series"}


def model_from_heading(heading: str | None, brand: str | None = None) -> str | None:
    """제목 문자열에서 시리즈/모델만 남긴다. 없으면/모호하면 None."""
    if not heading:
        return None
    kept: list[str] = []
    for tok in heading.replace("/", " ").split():
        t = tok.strip(".,()").strip()
        if not t:
            continue
        low = t.lower()
        if low in _STOP:
            continue
        if brand and low == str(brand).strip().lower():
            continue
        kept.append(t)
    m = " ".join(kept).strip()
    if not m or len(m) > 40:   # 문장 수준이면 제목 오인 → 비움
        return None
    return m
