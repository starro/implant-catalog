"""검수 단계 — FiftyOne 등록 + review→training 승급.

- register_fiftyone: review 이미지를 FiftyOne 데이터셋에 증분 등록 (사람 검수용).
  ⚠️ 큐레이션 시작 후 전체 재빌드 금지(태그 소실) → content_hash 기준 증분 add.
- promote: keep(승인)된 hash 를 training/ 으로 복사 + 매니페스트(approved) 추가 + labels.tsv export.
  데모(auto_approve)에선 review 배치 전체를 승급.

FiftyOne 은 지연 import — 미설치 환경에서도 Dagster 로드/수집은 동작.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import storage

DATASET = "drheri"   # 새 레포 전용 (PoC 'implants' 와 분리)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_fiftyone(records: list[dict], log=print) -> int:
    """review 레코드를 FiftyOne 데이터셋에 증분 등록. 미설치 시 건너뜀."""
    if not records:
        return 0
    try:
        import fiftyone as fo
    except Exception as e:  # noqa: BLE001
        log(f"[review] FiftyOne 미설치 — 등록 생략 ({e})")
        return 0

    if DATASET in fo.list_datasets():
        ds = fo.load_dataset(DATASET)
    else:
        ds = fo.Dataset(DATASET, persistent=True)
        for f in ["content_hash", "brand", "series", "surface", "model", "modality",
                  "stage", "source_id", "origin_url", "nearby_text"]:
            ds.add_sample_field(f, fo.StringField)

    existing = set(ds.values("content_hash")) if len(ds) else set()
    samples = []
    for r in records:
        if r["content_hash"] in existing:
            continue
        s = fo.Sample(filepath=str((storage.DATA_ROOT / r["path"]).resolve()))
        s["content_hash"] = r["content_hash"]
        s["brand"] = r.get("brand")
        s["series"] = r.get("series")
        s["surface"] = r.get("surface")
        s["model"] = r.get("model")
        s["modality"] = r.get("modality")
        s["stage"] = "review"
        s["source_id"] = r.get("source_id")
        s["origin_url"] = r.get("origin_url")
        s["nearby_text"] = (r.get("nearby_text") or "")[:500]
        samples.append(s)
    if samples:
        ds.add_samples(samples)
    log(f"[review] FiftyOne 등록 {len(samples)}장 (기존 {len(existing)})")
    return len(samples)


def promote(hashes: list[str], log=print) -> int:
    """review → training 승급. 이미지 복사 + 매니페스트(approved) + labels.tsv + FiftyOne stage 갱신."""
    review = storage.latest_by_hash(stage="review")
    promoted: list[dict] = []
    moves: dict[str, str] = {}   # content_hash -> training 절대경로 (FiftyOne 갱신용)
    for h in hashes:
        r = review.get(h)
        if not r:
            continue
        src = storage.DATA_ROOT / r["path"]
        if not src.exists():
            log(f"[review] 원본 없음, 건너뜀 {h}")
            continue
        ext = Path(src).suffix.lstrip(".") or "jpg"
        dst = storage.stage_image_path("training", r["brand"], r["series"], r["model"],
                                       r["modality"], h, ext)
        if not dst.exists():
            shutil.copy2(src, dst)
        promoted.append({
            **r,
            "stage": "training",
            "status": "approved",
            "path": storage.rel(dst),
            "approved_at": _now(),
        })
        moves[h] = str(dst.resolve())
    storage.append_manifest(promoted)
    storage.export_labels_tsv()
    _fiftyone_set_training(moves, log)
    log(f"[review] training 승급 {len(promoted)}장 + labels.tsv export")
    return len(promoted)


def _fiftyone_set_training(moves: dict[str, str], log=print) -> None:
    """승급된 content_hash 의 FiftyOne 샘플을 stage=training 으로 갱신 + filepath 를 training 본으로."""
    if not moves:
        return
    try:
        import fiftyone as fo
        from fiftyone import ViewField as F
    except Exception as e:  # noqa: BLE001
        log(f"[review] FiftyOne 미설치 — stage 갱신 생략 ({e})")
        return
    if DATASET not in fo.list_datasets():
        return
    ds = fo.load_dataset(DATASET)
    n = 0
    for h, path in moves.items():
        for s in ds.match(F("content_hash") == h):
            s["stage"] = "training"
            s["filepath"] = path
            s.save()
            n += 1
    log(f"[review] FiftyOne stage→training {n}장")
