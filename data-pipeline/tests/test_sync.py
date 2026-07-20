from drheri_pipeline import storage
from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.services import sync


def _seed_images(data_root):
    """review 단계 이미지 3장 + 실제 파일 생성."""
    with conn.session() as cx:
        doc = writes.create_document(
            cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
            source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
            default_pages="", default_series="_unknown", memo="")
        for h in ("k1", "k2", "r1"):
            p = storage.DATA_ROOT / "review" / f"{h}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"png")
            writes.record_image(cx, {
                "content_hash": h, "path": f"review/{h}.png", "brand": "Osstem",
                "series": "_unknown", "surface": None, "model": "_unknown",
                "modality": "catalog", "page_no": 1, "bbox": [0, 0, 1, 1]}, doc, None)
    return doc


def test_is_promotable_requires_all_three_labels():
    assert sync.is_promotable({"review_state": "kept", "brand": "Osstem",
                               "series": "TSIII", "model": "TSIII4010S"}) is True
    assert sync.is_promotable({"review_state": "kept", "brand": "Osstem",
                               "series": "TSIII", "model": "_unknown"}) is False
    assert sync.is_promotable({"review_state": "pending", "brand": "Osstem",
                               "series": "TSIII", "model": "TSIII4010S"}) is False


def test_run_sync_applies_tags_labels_and_promotion(data_root, monkeypatch):
    doc = _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "k1", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": "SA", "model": "TSIII4010S"},
        {"content_hash": "k2", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": None, "model": "_unknown"},
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"},
    ])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)

    out = sync.run_sync()
    assert out["kept"] == 2
    assert out["rejected"] == 1
    assert out["promoted"] == 1

    with conn.session() as cx:
        f = queries.funnel_for_document(cx, doc)
        k1 = cx.execute("SELECT * FROM image WHERE content_hash='k1'").fetchone()
        k2 = cx.execute("SELECT * FROM image WHERE content_hash='k2'").fetchone()
    assert f == {"extracted": 3, "training": 1, "rejected": 1, "pending": 1,
                 "unreviewed": 0, "label_incomplete": 1}
    assert k1["stage"] == "training"
    assert k1["surface"] == "SA"
    assert (storage.DATA_ROOT / k1["rel_path"]).exists()
    # 원래 위치(review/)에는 더 이상 파일이 없어야 "이동"이 증명된다 (복사가 아님).
    assert not (storage.DATA_ROOT / "review" / "k1.png").exists()
    # 라벨(model)이 비어있는 k2 는 kept 이지만 승급 대상에서 제외돼야 한다.
    assert k2["stage"] == "review"
    assert k2["review_state"] == "kept"


def test_rejected_file_is_moved_not_deleted(data_root, monkeypatch):
    _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"}])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)
    sync.run_sync()

    with conn.session() as cx:
        row = cx.execute("SELECT * FROM image WHERE content_hash='r1'").fetchone()
    assert row["stage"] == "rejected"
    assert row["rel_path"].startswith("rejected/")
    assert (storage.DATA_ROOT / row["rel_path"]).exists()      # 삭제가 아니라 이동
    # 원래 위치(review/)에는 더 이상 파일이 없어야 "이동"이 증명된다 (복사가 아님).
    assert not (storage.DATA_ROOT / "review" / "r1.png").exists()


def test_sync_log_is_recorded(data_root, monkeypatch):
    _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda: [])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)
    sync.run_sync()
    with conn.session() as cx:
        row = cx.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row["finished_at"]
