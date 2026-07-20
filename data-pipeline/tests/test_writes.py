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
