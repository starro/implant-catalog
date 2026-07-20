from drheri_pipeline import assets
from drheri_pipeline.db import conn, queries, writes

RECORDS = [
    {"content_hash": "a1", "path": "review/x/a1.png", "brand": "Osstem",
     "series": "_unknown", "surface": None, "model": "_unknown",
     "modality": "catalog", "page_no": 1, "bbox": [0, 0, 10, 10]},
    {"content_hash": "a2", "path": "review/x/a2.png", "brand": "Osstem",
     "series": "_unknown", "surface": None, "model": "_unknown",
     "modality": "catalog", "page_no": 2, "bbox": [0, 0, 10, 10]},
]


def _doc_and_run():
    with conn.session() as cx:
        doc = writes.create_document(
            cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
            source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
            default_pages="", default_series="_unknown", memo="")
        run = writes.create_run(cx, doc, 0.35, 200, "")
    return doc, run


def test_record_ingest_writes_images_and_origins(data_root):
    doc, run = _doc_and_run()
    n = assets.record_ingest(RECORDS, doc, run)
    assert n == 2
    with conn.session() as cx:
        f = queries.funnel_for_document(cx, doc)
    assert f["extracted"] == 2
    assert f["pending"] == 2


def test_record_ingest_skips_when_no_document(data_root):
    assert assets.record_ingest(RECORDS, 0, 0) == 0
    with conn.session() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM image").fetchone()["c"]
    assert n == 0


def test_record_ingest_is_idempotent_on_recollect(data_root):
    doc, run = _doc_and_run()
    assets.record_ingest(RECORDS, doc, run)
    assets.record_ingest(RECORDS, doc, run)
    with conn.session() as cx:
        f = queries.funnel_for_document(cx, doc)
    assert f["extracted"] == 2
