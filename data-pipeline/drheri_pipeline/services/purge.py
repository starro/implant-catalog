"""수집 초기화 — 문서는 유지하고 그 문서의 수집 결과만 지워 재수집 가능하게.

지우는 것: 이 문서 전용 이미지(다른 문서와 공유 안 되는 것)의 파일·DB 행·FiftyOne 샘플,
           그리고 그 문서의 수집 이력(run).
유지하는 것: 문서(URL·브랜드·설정)·원본 PDF·다른 문서와 공유되는 이미지.

FiftyOne 삭제는 delete_fiftyone_samples() 로 격리 — 미설치/오류여도 DB·파일 정리는 진행,
그리고 테스트에서 monkeypatch 하기 쉽게 한다.
"""
from __future__ import annotations

from drheri_pipeline import storage
from drheri_pipeline.db import conn

DATASET = "drheri"


def delete_fiftyone_samples(hashes: list[str]) -> int:
    """FiftyOne 데이터셋에서 주어진 content_hash 샘플 삭제. 삭제 수 반환. 미설치/오류 시 0."""
    if not hashes:
        return 0
    try:
        import fiftyone as fo
        from fiftyone import ViewField as F
    except Exception:  # noqa: BLE001
        return 0
    if DATASET not in fo.list_datasets():
        return 0
    ds = fo.load_dataset(DATASET)
    view = ds.match(F("content_hash").is_in(hashes))
    n = len(view)
    ds.delete_samples(view)
    return n


def reset_document(doc_id: int) -> dict | None:
    """문서의 수집 결과만 초기화. 문서가 없으면 None."""
    with conn.session() as cx:
        if cx.execute("SELECT id FROM document WHERE id=?", (doc_id,)).fetchone() is None:
            return None

        hashes = [r["content_hash"] for r in cx.execute(
            "SELECT content_hash FROM image_origin WHERE document_id=?", (doc_id,))]
        # 다른 문서와 공유되지 않는 '전용' 이미지만 완전 삭제 대상
        solo = [h for h in hashes if cx.execute(
            "SELECT COUNT(*) c FROM image_origin WHERE content_hash=? AND document_id<>?",
            (h, doc_id)).fetchone()["c"] == 0]
        kept_shared = len(hashes) - len(solo)

        files = []
        training = 0
        for h in solo:
            r = cx.execute("SELECT rel_path, stage, review_state FROM image WHERE content_hash=?",
                           (h,)).fetchone()
            if r:
                files.append(storage.DATA_ROOT / r["rel_path"])
                if r["stage"] == "training" or r["review_state"] != "pending":
                    training += 1
        deleted_runs = cx.execute(
            "SELECT COUNT(*) c FROM run WHERE document_id=?", (doc_id,)).fetchone()["c"]

    # 트랜잭션 밖: FiftyOne 샘플 + 파일 (되돌릴 수 없는 외부 작업)
    delete_fiftyone_samples(solo)
    removed_files = 0
    for f in files:
        try:
            if f.exists():
                f.unlink()
                removed_files += 1
        except OSError:
            pass

    # DB 삭제 (문서·브랜드는 유지)
    with conn.session() as cx:
        cx.execute("DELETE FROM image_origin WHERE document_id=?", (doc_id,))
        for h in solo:
            cx.execute("DELETE FROM image WHERE content_hash=?", (h,))
        cx.execute("DELETE FROM run WHERE document_id=?", (doc_id,))

    return {"deleted_images": len(solo), "deleted_files": removed_files,
            "deleted_runs": deleted_runs, "deleted_training": training,
            "kept_shared": kept_shared}
