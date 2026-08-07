"""미리라벨 크롭을 FiftyOne 'drheri' 데이터셋에 증분 등록.

기존 review.py 의 증분 등록 관례를 따르되 라벨 필드/needs_review 태그를 채운다.
등록 후엔 기존 sync(keep/reject)·promote 흐름이 그대로 처리한다."""
from __future__ import annotations

from .. import storage

DATASET = "drheri"

_STR_FIELDS = ["content_hash", "brand", "model", "diameter", "length",
               "part_number", "evidence", "modality", "stage", "source_id", "origin_url"]


def register_prelabeled(records: list[dict], log=print) -> int:
    if not records:
        return 0
    try:
        import fiftyone as fo
    except Exception as e:  # noqa: BLE001
        log(f"[fiftyone_writer] FiftyOne 미설치 — 등록 생략 ({e})")
        return 0

    if DATASET in fo.list_datasets():
        ds = fo.load_dataset(DATASET)
    else:
        ds = fo.Dataset(DATASET, persistent=True)
        for f in _STR_FIELDS:
            ds.add_sample_field(f, fo.StringField)
        ds.add_sample_field("ai_confidence", fo.FloatField)
        ds.add_sample_field("source_page", fo.IntField)

    existing = set(ds.values("content_hash")) if len(ds) else set()
    samples = []
    for r in records:
        if r["content_hash"] in existing:
            continue
        s = fo.Sample(filepath=str((storage.DATA_ROOT / r["path"]).resolve()))
        for f in ["content_hash", "brand", "model", "diameter", "length",
                  "part_number", "evidence"]:
            s[f] = r.get(f)
        s["ai_confidence"] = float(r.get("ai_confidence") or 0.0)
        s["source_page"] = int(r.get("source_page") or 0)
        s["modality"] = "catalog"
        s["stage"] = "review"
        s["source_id"] = "catalog_vlm"
        s["origin_url"] = r.get("origin_url")
        if r.get("needs_review"):
            s.tags.append("needs_review")
        samples.append(s)
    if samples:
        ds.add_samples(samples)
    log(f"[fiftyone_writer] 미리라벨 등록 {len(samples)}장 (기존 {len(existing)})")
    return len(samples)
