from drheri_pipeline import storage
from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.services import purge


def _seed_doc(cx, url, name="cat.pdf", brand="Osstem"):
    return writes.create_document(
        cx, brand_raw=brand, name=name, url=url, source_type="catalog_pdf",
        default_conf=0.35, default_dpi=200, default_pages="", default_series="_unknown", memo="")


def _add_image(cx, h, doc_id, brand="Osstem", stage="review", review_state="pending"):
    p = storage.DATA_ROOT / "review" / f"{h}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"png")
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, model, modality,
                              review_state, stage, rel_path, created_at)
           VALUES (?,'png',?, '_unknown','_unknown','catalog', ?, ?, ?, '2026-07-21T00:00:00+00:00')
           ON CONFLICT(content_hash) DO NOTHING""",
        (h, brand, review_state, stage, f"review/{h}.png"))
    cx.execute("""INSERT INTO image_origin (content_hash, document_id, created_at)
                  VALUES (?,?, '2026-07-21T00:00:00+00:00')
                  ON CONFLICT DO NOTHING""", (h, doc_id))


def test_reset_removes_collected_data_keeps_document(data_root, monkeypatch):
    monkeypatch.setattr(purge, "delete_fiftyone_samples", lambda hashes: len(hashes))
    with conn.session() as cx:
        doc = _seed_doc(cx, "https://ex.com/a.pdf")
        for h in ("h1", "h2", "h3"):
            _add_image(cx, h, doc)
        writes.create_run(cx, doc, 0.35, 200, "")

    result = purge.reset_document(doc)
    assert result["deleted_images"] == 3
    assert result["deleted_runs"] == 1
    assert result["kept_shared"] == 0

    with conn.session() as cx:
        # 문서는 유지
        assert queries.document_detail(cx, doc) is not None
        # 수집 결과는 0
        assert queries.funnel_for_document(cx, doc)["extracted"] == 0
        assert cx.execute("SELECT COUNT(*) c FROM image").fetchone()["c"] == 0
        assert cx.execute("SELECT COUNT(*) c FROM run WHERE document_id=?", (doc,)).fetchone()["c"] == 0
    # 전용 이미지 파일 삭제됨
    assert not (storage.DATA_ROOT / "review" / "h1.png").exists()


def test_reset_preserves_images_shared_with_other_document(data_root, monkeypatch):
    captured = {}
    monkeypatch.setattr(purge, "delete_fiftyone_samples",
                        lambda hashes: captured.setdefault("hashes", list(hashes)) or len(hashes))
    with conn.session() as cx:
        d1 = _seed_doc(cx, "https://ex.com/a.pdf")
        d2 = _seed_doc(cx, "https://ex.com/b.pdf")
        _add_image(cx, "solo", d1)
        _add_image(cx, "shared", d1)
        _add_image(cx, "shared", d2)          # shared 는 두 문서 소유

    result = purge.reset_document(d1)
    assert result["deleted_images"] == 1      # solo 만
    assert result["kept_shared"] == 1
    assert captured["hashes"] == ["solo"]     # FiftyOne 삭제도 solo 만

    with conn.session() as cx:
        # shared 이미지와 그 파일은 남아 d2 가 소유
        assert cx.execute("SELECT COUNT(*) c FROM image WHERE content_hash='shared'").fetchone()["c"] == 1
        assert cx.execute("SELECT COUNT(*) c FROM image_origin WHERE content_hash='shared'").fetchone()["c"] == 1
        assert queries.funnel_for_document(cx, d2)["extracted"] == 1
    assert (storage.DATA_ROOT / "review" / "shared.png").exists()
    assert not (storage.DATA_ROOT / "review" / "solo.png").exists()


def test_reset_reports_training_count(data_root, monkeypatch):
    monkeypatch.setattr(purge, "delete_fiftyone_samples", lambda hashes: 0)
    with conn.session() as cx:
        doc = _seed_doc(cx, "https://ex.com/a.pdf")
        _add_image(cx, "t1", doc, stage="training", review_state="kept")
        _add_image(cx, "p1", doc)
    result = purge.reset_document(doc)
    assert result["deleted_images"] == 2
    assert result["deleted_training"] == 1    # 프론트 경고용


def test_reset_missing_document_returns_none(data_root):
    assert purge.reset_document(9999) is None
