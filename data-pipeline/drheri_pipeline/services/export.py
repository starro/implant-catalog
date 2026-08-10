"""DGX 내보내기 — SQLite 의 training 이미지를 labels.tsv / manifest.jsonl 로 평탄화.

우리 DB 는 brand/series/surface/model 을 분해 저장한다. 내보낼 때만 DGX 표기로
브랜드를 정규화하고 series+surface 를 합성한다(예: 'TSIII'+'SA' → 'TSIII SA').
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from drheri_pipeline import storage
from drheri_pipeline.db import conn
from drheri_pipeline.taxonomy import compose_series, normalize_brand

_TRAINING = "SELECT * FROM image WHERE stage='training' ORDER BY content_hash"


def _dgx_row(r: sqlite3.Row) -> tuple[str, str, str, str]:
    brand = normalize_brand(r["brand"]) or "_unknown"
    series = compose_series(r["series"], r["surface"]) or "_unknown"
    model = r["model"] or "_unknown"
    train_root = storage.DATA_ROOT / "training"
    abs_path = (storage.DATA_ROOT / r["rel_path"]).resolve()
    try:
        rel = abs_path.relative_to(train_root).as_posix()
    except ValueError:                      # training/ 밖이면 DATA_ROOT 기준 경로 그대로
        rel = Path(r["rel_path"]).as_posix()
    return brand, series, model, rel


def export_all() -> dict:
    tsv_path = storage.DATA_ROOT / "training" / "labels.tsv"
    jsonl_path = storage.DATA_ROOT / "export" / "manifest.jsonl"
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    rows = 0
    with conn.session() as cx, \
            tsv_path.open("w", encoding="utf-8") as tsv, \
            jsonl_path.open("w", encoding="utf-8") as jl:
        # 지름·길이는 필수 스펙 → tsv 에 컬럼으로 포함(없으면 빈칸). 코드는 jsonl 에만(옵션).
        tsv.write("brand\tseries\tmodel\tdiameter\tlength\trel_path\n")
        for r in cx.execute(_TRAINING).fetchall():
            brand, series, model, rel = _dgx_row(r)
            dia = r["diameter"] or ""
            length = r["length"] or ""
            tsv.write(f"{brand}\t{series}\t{model}\t{dia}\t{length}\t{rel}\n")
            jl.write(json.dumps({**dict(r), "dgx_brand": brand, "dgx_series": series},
                                ensure_ascii=False) + "\n")
            rows += 1

    return {"labels_tsv": storage.rel(tsv_path),
            "manifest_jsonl": storage.rel(jsonl_path),
            "rows": rows}


def class_distribution(cx: sqlite3.Connection) -> dict:
    """training 기준 클래스 분포 (DGX 표기로 집계)."""
    brands: dict[str, int] = {}
    series: dict[str, int] = {}
    models: dict[str, int] = {}
    total = 0
    for r in cx.execute(_TRAINING).fetchall():
        b, s, m, _ = _dgx_row(r)
        brands[b] = brands.get(b, 0) + 1
        series[s] = series.get(s, 0) + 1
        models[m] = models.get(m, 0) + 1
        total += 1

    def _top(d: dict) -> list[dict]:
        return [{"name": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))]

    return {"brands": _top(brands), "series": _top(series), "models": _top(models), "total": total}
