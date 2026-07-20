"""DGX 라벨 taxonomy 정렬 — 브랜드 별칭 + series 합성.

우리 manifest(jsonl) 는 brand/series/surface/model 을 **분해 저장**(원자 단위)한다.
DGX labels.tsv 로 export 할 때만 이 모듈로 브랜드를 DGX 표기로 정규화하고 series+surface 를 합성한다.
→ 우리 라벨은 유연하게(표면 따로 검색·통계), DGX 로는 교집합 가능하게.

DGX 브랜드 표기 (2026-06-24 labels.tsv 확인):
  DENTIUM / DIO IMPLANT / Dentsply Sirona / NEOBIOTECH / Nobel Biocare /
  OSSTEM IMPLANT / Point Implant / Straumann
"""

BRAND_ALIASES = {
    "osstem": "OSSTEM IMPLANT",
    "osstem implant": "OSSTEM IMPLANT",
    "dio": "DIO IMPLANT",
    "dio implant": "DIO IMPLANT",
    "dentium": "DENTIUM",
    "neobiotech": "NEOBIOTECH",
    "nobel": "Nobel Biocare",
    "nobel biocare": "Nobel Biocare",
    "dentsply": "Dentsply Sirona",
    "dentsply sirona": "Dentsply Sirona",
    "straumann": "Straumann",
    "point": "Point Implant",
    "point implant": "Point Implant",
}


def normalize_brand(brand: str | None) -> str | None:
    """우리 브랜드 표기 → DGX 표기 (예: 'Osstem' → 'OSSTEM IMPLANT'). 모르면 원본 유지."""
    if not brand:
        return brand
    return BRAND_ALIASES.get(brand.strip().lower(), brand.strip())


def compose_series(series: str | None, surface: str | None = None) -> str:
    """분해된 series+surface → DGX 표기 ('TSIII'+'SA' → 'TSIII SA'). surface 없으면 series 그대로."""
    s = (series or "").strip()
    su = (surface or "").strip()
    if su and not s.endswith(su):
        return f"{s} {su}".strip()
    return s
