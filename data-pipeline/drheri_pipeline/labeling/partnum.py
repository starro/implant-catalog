"""part_number → length(mm) 파서.

브랜드별 포맷이 제각각이라 v1 은 범용 규칙: 문자열에서 임플란트 길이로 그럴듯한
mm 값(6~20)을 뽑는다. 브랜드별 정밀 규칙은 BRAND_RULES 에 추가(확장 훅)."""
from __future__ import annotations

import re

_NUM = re.compile(r"\d+(?:\.\d+)?")

# 브랜드별 정밀 파서 확장 지점 (v1 비어있음). 값은 (part_number)->str|None 함수.
BRAND_RULES: dict[str, "callable"] = {}


def _generic_length(part_number: str) -> str | None:
    """6~20mm 범위의 마지막 그럴듯한 값 = length 후보(직경 3~7 과 구분)."""
    cands = [t for t in _NUM.findall(part_number) if 6.0 <= float(t) <= 20.0]
    if not cands:
        return None
    v = cands[-1]
    return v[:-2] if v.endswith(".0") else v


def parse_length(brand: str | None, part_number: str | None) -> str | None:
    if not part_number:
        return None
    rule = BRAND_RULES.get((brand or "").strip().lower())
    if rule:
        got = rule(part_number)
        if got:
            return got
    return _generic_length(part_number)
