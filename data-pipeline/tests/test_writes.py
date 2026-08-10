import pytest

from drheri_pipeline.db import conn, writes


def _doc(cx, url="https://ex.com/a.pdf"):
    return writes.create_document(
        cx, brand_raw="Osstem", name="TS 카탈로그", url=url,
        source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
        default_pages="", default_series="_unknown", memo="",
    )


def test_upsert_brand_normalizes_and_dedupes(data_root):
    with conn.session() as cx:
        a = writes.upsert_brand(cx, "Osstem")
        b = writes.upsert_brand(cx, "osstem implant")
    assert a == b
    with conn.session() as cx:
        row = cx.execute("SELECT name_norm FROM brand WHERE id=?", (a,)).fetchone()
    assert row["name_norm"] == "OSSTEM IMPLANT"


def test_create_document_rejects_duplicate_url(data_root):
    with conn.session() as cx:
        _doc(cx)
    with pytest.raises(writes.DuplicateUrl):
        with conn.session() as cx:
            _doc(cx)


def test_run_lifecycle(data_root):
    with conn.session() as cx:
        doc = _doc(cx)
        run = writes.create_run(cx, doc, 0.35, 200, "1,2")
        writes.attach_dagster_run(cx, run, "abc123")
        writes.finish_run(cx, run, "SUCCESS", 7, None)
        row = cx.execute("SELECT * FROM run WHERE id=?", (run,)).fetchone()
    assert row["status"] == "SUCCESS"
    assert row["extracted"] == 7
    assert row["dagster_run_id"] == "abc123"
    assert row["finished_at"]


def test_record_image_is_idempotent_and_links_origin(data_root):
    rec = {
        "content_hash": "h1", "path": "review/x/h1.png", "brand": "Osstem",
        "series": "_unknown", "surface": None, "model": "_unknown",
        "modality": "catalog", "page_no": 3, "bbox": [1, 2, 3, 4],
    }
    with conn.session() as cx:
        doc = _doc(cx)
        run = writes.create_run(cx, doc, 0.35, 200, "")
        writes.record_image(cx, rec, doc, run)
        writes.record_image(cx, rec, doc, run)      # 재수집 — 부풀지 않아야 함
        imgs = cx.execute("SELECT COUNT(*) c FROM image").fetchone()["c"]
        orgs = cx.execute("SELECT COUNT(*) c FROM image_origin").fetchone()["c"]
    assert imgs == 1
    assert orgs == 1


def test_record_image_persists_specs(data_root):
    # 지름/길이/코드가 image 테이블에 저장되어야 export(jsonl=dict(r))로 흐른다
    rec = {
        "content_hash": "s1", "path": "review/x/s1.png", "brand": "Hiossen",
        "series": "_unknown", "surface": None, "model": "ETIII NH", "modality": "catalog",
        "diameter": "4.5", "diameter_src": "vlm_mark", "length": "7", "length_src": "vlm_mark",
        "part_number": "ET3R4507B", "part_number_src": "vlm_mark",
        "is_fixture": True, "page_no": 3, "bbox": [1, 2, 3, 4],
    }
    with conn.session() as cx:
        doc = _doc(cx)
        writes.record_image(cx, rec, doc, None)
        row = cx.execute("SELECT * FROM image WHERE content_hash='s1'").fetchone()
    assert row["diameter"] == "4.5" and row["length"] == "7"
    assert row["length_src"] == "vlm_mark" and row["part_number"] == "ET3R4507B"


def test_same_image_from_two_documents_has_two_origins(data_root):
    rec = {"content_hash": "h1", "path": "review/x/h1.png", "brand": "Osstem",
           "series": "_unknown", "surface": None, "model": "_unknown",
           "modality": "catalog", "page_no": 1, "bbox": [0, 0, 1, 1]}
    with conn.session() as cx:
        d1 = _doc(cx, "https://ex.com/a.pdf")
        d2 = _doc(cx, "https://ex.com/b.pdf")
        writes.record_image(cx, rec, d1, None)
        writes.record_image(cx, rec, d2, None)
        imgs = cx.execute("SELECT COUNT(*) c FROM image").fetchone()["c"]
        orgs = cx.execute("SELECT COUNT(*) c FROM image_origin").fetchone()["c"]
    assert imgs == 1
    assert orgs == 2


def test_update_document_changes_editable_fields(data_root):
    """허용 필드(name, memo, default_dpi 등)가 실제로 업데이트되고 updated_at이 갱신된다."""
    with conn.session() as cx:
        doc = _doc(cx)
        row_before = cx.execute("SELECT name, memo, default_dpi, updated_at FROM document WHERE id=?", (doc,)).fetchone()

    import time
    time.sleep(0.01)  # 시간 경과 명확히

    with conn.session() as cx:
        writes.update_document(cx, doc, name="새 이름", memo="새로운 메모", default_dpi=300)
        row_after = cx.execute("SELECT name, memo, default_dpi, updated_at FROM document WHERE id=?", (doc,)).fetchone()

    assert row_after["name"] == "새 이름"
    assert row_after["memo"] == "새로운 메모"
    assert row_after["default_dpi"] == 300
    assert row_after["updated_at"] > row_before["updated_at"]


def test_update_document_ignores_non_editable_fields(data_root):
    """화이트리스트 밖 필드(url, status 등)는 무시되고 DB 값이 그대로이다."""
    with conn.session() as cx:
        doc = _doc(cx, "https://ex.com/original.pdf")
        original_url = cx.execute("SELECT url, status FROM document WHERE id=?", (doc,)).fetchone()

    with conn.session() as cx:
        # url과 status는 화이트리스트에 없으므로 무시되어야 함
        writes.update_document(cx, doc, url="https://ex.com/hacked.pdf", status="archived", name="수정됨")
        row = cx.execute("SELECT url, status, name FROM document WHERE id=?", (doc,)).fetchone()

    # url과 status는 그대로, name만 변경됨
    assert row["url"] == original_url["url"]
    assert row["status"] == original_url["status"]
    assert row["name"] == "수정됨"


def test_update_document_converts_brand_raw_to_brand_id(data_root):
    """brand_raw를 전달하면 새 브랜드로 변환되고 brand_id가 갱신된다."""
    with conn.session() as cx:
        doc = _doc(cx, "https://ex.com/doc1.pdf")
        row_before = cx.execute("SELECT brand_id FROM document WHERE id=?", (doc,)).fetchone()
        brand_before = row_before["brand_id"]

    with conn.session() as cx:
        writes.update_document(cx, doc, brand_raw="Dentium")
        row_after = cx.execute("SELECT brand_id FROM document WHERE id=?", (doc,)).fetchone()
        brand_after = row_after["brand_id"]

    assert brand_before != brand_after
    with conn.session() as cx:
        brand_name = cx.execute("SELECT name_norm FROM brand WHERE id=?", (brand_after,)).fetchone()
    assert brand_name["name_norm"] == "DENTIUM"


def test_archive_document_sets_status_and_updates_timestamp(data_root):
    """archive_document가 status를 'archived'로 설정하고 updated_at을 갱신한다."""
    with conn.session() as cx:
        doc = _doc(cx)
        row_before = cx.execute("SELECT status, updated_at FROM document WHERE id=?", (doc,)).fetchone()
        assert row_before["status"] == "active"

    import time
    time.sleep(0.01)

    with conn.session() as cx:
        writes.archive_document(cx, doc)
        row_after = cx.execute("SELECT status, updated_at FROM document WHERE id=?", (doc,)).fetchone()

    assert row_after["status"] == "archived"
    assert row_after["updated_at"] > row_before["updated_at"]


def test_record_image_preserves_manual_labels_on_rescan(data_root):
    """재수집 시 사람이 고친 라벨을 덮어쓰지 않는다.

    1. 수집: content_hash=h1, brand=Osstem, series=_unknown, model=_unknown
    2. 사람 검수: brand=DENTIUM, series=TSIII, model=TSIII4010S로 수정
    3. 재수집: 같은 content_hash, 다른 라벨(Amann Girrbach, GC, GC55)
    4. 검증: 사람이 고친 라벨 유지
    """
    rec_v1 = {
        "content_hash": "h_manual_test", "path": "review/x/h_manual.png",
        "brand": "Osstem", "series": "_unknown", "surface": None, "model": "_unknown",
        "modality": "catalog", "page_no": 1, "bbox": [0, 0, 10, 10],
    }
    rec_v2 = {
        "content_hash": "h_manual_test",  # 같은 hash
        "path": "review/y/h_manual_v2.png",
        "brand": "Amann Girrbach",  # 다른 라벨
        "series": "GC",
        "surface": None,
        "model": "GC55",
        "modality": "catalog",
        "page_no": 2,
        "bbox": [5, 5, 15, 15],
    }

    with conn.session() as cx:
        doc = _doc(cx)
        run1 = writes.create_run(cx, doc, 0.35, 200, "")
        # 첫 번째 수집
        writes.record_image(cx, rec_v1, doc, run1)
        img_v1 = cx.execute(
            "SELECT brand, series, model FROM image WHERE content_hash=?",
            ("h_manual_test",)
        ).fetchone()

        # 사람이 검수 후 라벨 수정
        cx.execute(
            "UPDATE image SET brand=?, series=?, model=? WHERE content_hash=?",
            ("DENTIUM", "TSIII", "TSIII4010S", "h_manual_test")
        )
        img_after_manual = cx.execute(
            "SELECT brand, series, model FROM image WHERE content_hash=?",
            ("h_manual_test",)
        ).fetchone()
        assert img_after_manual["brand"] == "DENTIUM"
        assert img_after_manual["model"] == "TSIII4010S"

    # 재수집 — 다른 라벨로 들어옴
    with conn.session() as cx:
        run2 = writes.create_run(cx, doc, 0.35, 200, "")
        writes.record_image(cx, rec_v2, doc, run2)
        img_after_rescan = cx.execute(
            "SELECT brand, series, model FROM image WHERE content_hash=?",
            ("h_manual_test",)
        ).fetchone()

    # 사람이 고친 라벨이 유지되어야 함
    assert img_after_rescan["brand"] == "DENTIUM"
    assert img_after_rescan["series"] == "TSIII"
    assert img_after_rescan["model"] == "TSIII4010S"


def test_record_image_stores_new_fields(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn, writes
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    conn.migrate()
    rec = {"content_hash": "h1", "path": "review/BEGO/catalog/h1.png", "brand": "BEGO",
           "model": "SC", "modality": "catalog", "page_no": 18, "bbox": [1, 2, 3, 4],
           "is_fixture": True, "diameter": "4.1", "diameter_src": "geom", "needs_review": False}
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u1",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        writes.record_image(cx, rec, d, None)
    cx = conn.connect()
    row = cx.execute("SELECT is_fixture, diameter, diameter_src, needs_review "
                     "FROM image WHERE content_hash='h1'").fetchone()
    cx.close()
    assert row["diameter"] == "4.1" and row["diameter_src"] == "geom"
    assert row["is_fixture"] == 1 and row["needs_review"] == 0
