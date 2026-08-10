"""미리라벨 크롭을 FiftyOne 'drheri' 데이터셋에 증분 등록.

기존 review.py 의 증분 등록 관례를 따르되 라벨 필드/needs_review 태그를 채운다.
등록 후엔 기존 sync(keep/reject)·promote 흐름이 그대로 처리한다.

각 샘플에 `document_id`(관리 DB document.id) 를 심고, 문서별 saved view `doc-<id>`
를 만들어 UI 의 "이 문서만 보기"(?view=doc-<id>) 딥링크가 걸리도록 한다."""
from __future__ import annotations

from .. import storage

DATASET = "drheri"

_STR_FIELDS = ["content_hash", "brand", "model", "diameter", "length",
               "part_number", "evidence", "modality", "stage", "source_id", "origin_url"]


def _ensure_field(ds, name, field_type) -> None:
    """데이터셋(신규/기존)에 없는 필드면 추가한다."""
    if name not in ds.get_field_schema():
        ds.add_sample_field(name, field_type)


def _ensure_doc_view(ds, document_id: int, log=print) -> None:
    """문서 하나만 거르는 saved view `doc-<id>` 를 생성/갱신. 이름=슬러그 라 ?view=doc-<id> 로 열린다."""
    import fiftyone as fo  # noqa: F401
    from fiftyone import ViewField as F
    name = f"doc-{int(document_id)}"
    view = ds.match(F("document_id") == int(document_id))
    if name in ds.list_saved_views():
        ds.delete_saved_view(name)                 # save_view 는 중복 이름을 거부 → 지우고 다시
    ds.save_view(name, view)
    log(f"[fiftyone_writer] saved view {name} ({len(view)}장)")


def register_prelabeled(records: list[dict], document_id: int | None = None,
                        log=print) -> int:
    if not records:
        return 0
    try:
        import fiftyone as fo
    except Exception as e:  # noqa: BLE001
        log(f"[fiftyone_writer] FiftyOne 미설치 — 등록 생략 ({e})")
        return 0

    if DATASET in fo.list_datasets():
        ds = fo.load_dataset(DATASET)
        _ensure_field(ds, "document_id", fo.IntField)   # 구 데이터셋엔 없을 수 있다
    else:
        ds = fo.Dataset(DATASET, persistent=True)
        for f in _STR_FIELDS:
            ds.add_sample_field(f, fo.StringField)
        ds.add_sample_field("ai_confidence", fo.FloatField)
        ds.add_sample_field("source_page", fo.IntField)
        ds.add_sample_field("is_fixture", fo.BooleanField)
        ds.add_sample_field("document_id", fo.IntField)

    existing = set(ds.values("content_hash")) if len(ds) else set()
    samples = []
    for r in records:
        if r["content_hash"] in existing:
            continue
        existing.add(r["content_hash"])
        s = fo.Sample(filepath=str((storage.DATA_ROOT / r["path"]).resolve()))
        for f in ["content_hash", "brand", "model", "diameter", "length",
                  "part_number", "evidence"]:
            s[f] = r.get(f)
        s["ai_confidence"] = float(r.get("ai_confidence") or 0.0)
        s["source_page"] = int(r.get("source_page") or 0)
        s["is_fixture"] = r.get("is_fixture")     # bool|None (검수 필터용, 버리진 않음)
        s["modality"] = "catalog"
        s["stage"] = "review"
        s["source_id"] = "catalog_vlm"
        s["origin_url"] = r.get("origin_url")
        if document_id is not None:
            s["document_id"] = int(document_id)   # "이 문서만 보기" 필터 키
        if r.get("needs_review"):
            s.tags.append("needs_review")
        if r.get("is_fixture") is False:          # VLM 이 '픽스처 아님' 판단 → 발라내기 필터 태그
            s.tags.append("not_fixture")
        samples.append(s)
    if samples:
        ds.add_samples(samples)
    log(f"[fiftyone_writer] 미리라벨 등록 {len(samples)}장 (기존 {len(existing)})")
    if document_id is not None:
        _ensure_doc_view(ds, document_id, log=log)
    return len(samples)


def backfill_document_ids(log=print) -> dict:
    """기존 샘플에 `document_id` 를 소급 기입하고 문서별 saved view 를 만든다(1회 실행).

    관리 DB 의 image_origin(content_hash → document_id) 을 진실의 출처로 삼는다.
    한 이미지가 여러 문서에 속하면 결정적으로 최소 document_id 를 채택한다(IntField 는 단일값).
    """
    try:
        import fiftyone as fo
    except Exception as e:  # noqa: BLE001
        log(f"[backfill] FiftyOne 미설치 — 중단 ({e})")
        return {"tagged": 0, "docs": 0}
    from drheri_pipeline.db import conn

    if DATASET not in fo.list_datasets():
        log("[backfill] drheri 데이터셋 없음 — 할 일 없음")
        return {"tagged": 0, "docs": 0}
    ds = fo.load_dataset(DATASET)
    _ensure_field(ds, "document_id", fo.IntField)

    with conn.session() as cx:
        rows = cx.execute("SELECT content_hash, document_id FROM image_origin").fetchall()
    mapping: dict[str, int] = {}
    for r in rows:
        h, d = r["content_hash"], int(r["document_id"])
        if h not in mapping or d < mapping[h]:
            mapping[h] = d

    hashes = ds.values("content_hash")
    ids = [mapping.get(h) for h in hashes]
    ds.set_values("document_id", ids)

    docs = sorted({d for d in ids if d is not None})
    for d in docs:
        _ensure_doc_view(ds, d, log=log)
    tagged = sum(1 for i in ids if i is not None)
    log(f"[backfill] document_id {tagged}/{len(ids)}장 기입, saved view {len(docs)}개")
    return {"tagged": tagged, "docs": len(docs)}


if __name__ == "__main__":       # DGX 호스트에서 1회: DATA_ROOT=... python -m ...fiftyone_writer
    backfill_document_ids()
