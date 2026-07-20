"""문서별 FiftyOne saved view 생성 — 상세 화면의 "이 문서만 보기" 링크 대상.

뷰 이름은 doc-<document_id>. 기존 뷰는 덮어쓴다(뷰 정의만 갱신, 샘플은 건드리지 않음).
실행: FIFTYONE_DATABASE_VALIDATION=false .venv/Scripts/python -m scripts.fiftyone_saved_views
"""
from __future__ import annotations

from drheri_pipeline.db import conn

DATASET = "drheri"


def sync_views() -> int:
    import fiftyone as fo
    from fiftyone import ViewField as F

    if DATASET not in fo.list_datasets():
        return 0
    ds = fo.load_dataset(DATASET)

    with conn.session() as cx:
        rows = cx.execute("SELECT id, name FROM document WHERE status='active'").fetchall()
        origins = {r["id"]: [x["content_hash"] for x in cx.execute(
            "SELECT content_hash FROM image_origin WHERE document_id=?", (r["id"],)).fetchall()]
            for r in rows}

    made = 0
    for r in rows:
        hashes = origins.get(r["id"]) or []
        if not hashes:
            continue
        name = f"doc-{r['id']}"
        if name in ds.list_saved_views():
            ds.delete_saved_view(name)
        ds.save_view(name, ds.match(F("content_hash").is_in(hashes)),
                     description=r["name"])
        made += 1

    # 버림 전용 뷰 — 오판 복구용
    if "버림" in ds.list_saved_views():
        ds.delete_saved_view("버림")
    ds.save_view("버림", ds.match(F("stage") == "rejected"), description="버림 처리된 이미지")
    return made


if __name__ == "__main__":
    print(f"saved views {sync_views()}개 생성")
