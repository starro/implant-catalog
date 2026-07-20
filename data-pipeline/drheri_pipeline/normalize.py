"""라벨/경로 정규화.

DGX 실측 버그: 시리즈명이 `NobelActive TiUltra｜WP`(전각파이프 붙임)와
`NobelActive TiUltra ｜ WP`(공백 포함) 두 디렉토리로 갈리던 문제 → 여기서 통일.
"""
import re

# Windows 파일시스템 금지문자 (ascii '|' 포함). 전각 '｜' 는 허용되므로 시리즈명엔 전각을 쓴다.
_ILLEGAL = re.compile(r'[\\/:*?"<>]')


def normalize_series(name: str | None) -> str:
    """시리즈명 표준화 — 파이프를 전각 '｜'로 통일하고 주변 공백 제거, 다중 공백 축약.

    예) 'NobelActive TiUltra ｜ WP' → 'NobelActive TiUltra｜WP'
        'Astra Tech|OsseoSpeed TX'  → 'Astra Tech｜OsseoSpeed TX'
    """
    if not name:
        return ""
    s = name.replace("|", "｜")           # ascii 파이프 → 전각 (DGX labels.tsv 표기와 일치)
    s = re.sub(r"\s*｜\s*", "｜", s)        # 전각 파이프 주변 공백 제거
    s = re.sub(r"\s+", " ", s).strip()    # 다중 공백 축약
    return s


def normalize_model(name: str | None, *, fallback: str = "_unknown") -> str:
    """제품코드(model) 표준화 — 대문자 통일 + 공백 축약.

    제품코드는 케이스무관 식별자라 원본 파일명 casing 이 제각각(tsIIS4008S vs TSIIS4010S)
    → 같은 제품이 다른 디렉토리로 갈리는 것 방지. DGX labels.tsv 의 모델(US4R4010S 등)이
    전부 대문자인 것과도 일치.

    예) 'tsIIS4008S' → 'TSIIS4008S'.  '_unknown' 등 sentinel 은 보존.
    """
    if not name:
        return fallback
    s = name.strip()
    if s.startswith("_"):              # _unknown 같은 sentinel 보존
        return s
    s = _ILLEGAL.sub("_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper() or fallback


def safe_component(name: str | None, *, fallback: str = "_unknown") -> str:
    """디렉토리 한 칸으로 안전한 문자열. 금지문자 치환, 빈 값은 fallback."""
    if not name:
        return fallback
    s = name.replace("|", "｜")
    s = _ILLEGAL.sub("_", s).strip().strip(".")
    return s or fallback
