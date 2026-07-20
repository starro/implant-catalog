"""로컬 스토리지 — 단계별 디렉토리, content-hash 파일명, 매니페스트(jsonl) + labels.tsv export.

디렉토리 체계 (설계 §3):
    data/
      raw/      <brand>/<source>/<file>            # 추출 전 (PDF 등)
      review/   <brand>/<series>/<model>/<modality>/<hash>.<ext>
      training/ <brand>/<series>/<model>/<modality>/<hash>.<ext>
                labels.tsv                          # DGX export

메타데이터(설계 §9, 2단):
    manifest.jsonl  = 유일 출처 (provenance·bbox·옵션필드 native, stage 로 review/training 구분)
    training/labels.tsv = 위를 평탄화한 DGX 학습 인덱스
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .normalize import safe_component

DATA_ROOT = Path(os.getenv("DATA_ROOT", "./data")).resolve()
MANIFEST = DATA_ROOT / "manifest.jsonl"


# ---- 해시 / 경로 ----------------------------------------------------------

def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(p: Path) -> str:
    """DATA_ROOT 기준 상대경로 (POSIX 슬래시)."""
    return p.resolve().relative_to(DATA_ROOT).as_posix()


def stage_image_path(stage: str, brand: str, series: str, model: str,
                     modality: str, hash_: str, ext: str = "jpg") -> Path:
    """review/training 의 이미지 경로. 부모 디렉토리 자동 생성.

    식별 안 된 레벨(_unknown/빈값)은 경로에서 생략 → `Osstem/SSII/catalog/` 처럼 깔끔.
    라벨의 출처는 manifest 이므로 디렉토리는 가변 깊이여도 무방(사람 보기용).
    """
    assert stage in ("review", "training")
    p = DATA_ROOT / stage / safe_component(brand)
    for level in (series, model):                 # 미상이면 디렉토리 생략
        if level and level != "_unknown":
            p = p / safe_component(level)
    p = p / safe_component(modality) / f"{hash_}.{ext}"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def raw_path(brand: str, source_id: str, filename: str) -> Path:
    """raw 원본(PDF 등) 경로. brand 까지만 확정, 그 아래 source 단위."""
    p = DATA_ROOT / "raw" / safe_component(brand) / safe_component(source_id) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---- 매니페스트 (jsonl) ---------------------------------------------------

def append_manifest(records: list[dict]) -> None:
    if not records:
        return
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def latest_by_hash(stage: str | None = None) -> dict[str, dict]:
    """content_hash 별 최신 레코드 (append-only 로그에서 최신만 채택)."""
    out: dict[str, dict] = {}
    for r in read_manifest():
        if stage and r.get("stage") != stage:
            continue
        out[r["content_hash"]] = r  # 뒤(최신)가 앞을 덮어씀
    return out


# ---- DGX export (labels.tsv) ---------------------------------------------

def export_labels_tsv() -> Path:
    """training 승인분을 DGX `labels.tsv` 동형으로 export.

    우리 manifest 는 brand/series/surface/model 을 분해 저장 → export 시
    브랜드 정규화(Osstem→OSSTEM IMPLANT) + series+surface 합성(TSIII+SA→'TSIII SA').
    """
    from .taxonomy import compose_series, normalize_brand
    rows = latest_by_hash(stage="training")
    out = DATA_ROOT / "training" / "labels.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    train_root = DATA_ROOT / "training"
    with out.open("w", encoding="utf-8") as f:
        f.write("brand\tseries\tmodel\trel_path\n")
        for r in rows.values():
            rel_path = Path((DATA_ROOT / r["path"])).resolve().relative_to(train_root).as_posix()
            brand = normalize_brand(r.get("brand")) or "_unknown"
            series = compose_series(r.get("series"), r.get("surface")) or "_unknown"
            f.write(f'{brand}\t{series}\t{r.get("model", "_unknown")}\t{rel_path}\n')
    return out
