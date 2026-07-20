import json

from drheri_pipeline import storage
from drheri_pipeline.db import conn, writes
from drheri_pipeline.services import export


def _seed(cx):
    doc = writes.create_document(
        cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
        source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
        default_pages="", default_series="_unknown", memo="")
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, surface, model, modality,
                              review_state, stage, rel_path, created_at)
           VALUES ('t1','png','Osstem','TSIII','SA','TSIII4010S','catalog',
                   'kept','training','training/a/t1.png','2026-07-20T00:00:00+00:00')""")
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, model, modality,
                              review_state, stage, rel_path, created_at)
           VALUES ('p1','png','Osstem','TSIII','_unknown','catalog',
                   'pending','review','review/a/p1.png','2026-07-20T00:00:00+00:00')""")
    for h in ("t1", "p1"):
        cx.execute("""INSERT INTO image_origin (content_hash, document_id, created_at)
                      VALUES (?,?,'2026-07-20T00:00:00+00:00')""", (h, doc))


def test_export_writes_only_training_rows_with_dgx_labels(data_root):
    with conn.session() as cx:
        _seed(cx)
    out = export.export_all()
    assert out["rows"] == 1

    tsv = (storage.DATA_ROOT / out["labels_tsv"]).read_text(encoding="utf-8").splitlines()
    assert tsv[0] == "brand\tseries\tmodel\trel_path"
    assert tsv[1] == "OSSTEM IMPLANT\tTSIII SA\tTSIII4010S\ta/t1.png"   # 정규화 + series 합성

    lines = (storage.DATA_ROOT / out["manifest_jsonl"]).read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["content_hash"] == "t1"


def test_class_distribution_counts_training_only(data_root):
    with conn.session() as cx:
        _seed(cx)
        dist = export.class_distribution(cx)
    assert dist["total"] == 1
    assert dist["brands"] == [{"name": "OSSTEM IMPLANT", "count": 1}]
    assert dist["models"] == [{"name": "TSIII4010S", "count": 1}]


def _seed_multi_series(cx):
    """series 는 compose_series(series, surface) 로 두 컬럼을 합성하는 가장 복잡한 파생값이라
    별도로 브랜드/모델보다 많은 조합으로 시딩해 집계가 series 별로 올바른지 검증한다."""
    doc = writes.create_document(
        cx, brand_raw="Osstem", name="Multi", url="https://ex.com/multi.pdf",
        source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
        default_pages="", default_series="_unknown", memo="")
    rows = [
        ("m1", "TSIII", "SA", "TSIII4010S"),
        ("m2", "TSIII", "SA", "TSIII4010S"),
        ("m3", "TSIII", "RBM", "TSIII4010S"),
        ("m4", "SSII", None, "SSII4010"),
    ]
    for h, series, surface, model in rows:
        cx.execute(
            """INSERT INTO image (content_hash, ext, brand, series, surface, model, modality,
                                  review_state, stage, rel_path, created_at)
               VALUES (?,'png','Osstem',?,?,?, 'catalog','kept','training',?,
                       '2026-07-20T00:00:00+00:00')""",
            (h, series, surface, model, f"training/m/{h}.png"))
        cx.execute("""INSERT INTO image_origin (content_hash, document_id, created_at)
                      VALUES (?,?,'2026-07-20T00:00:00+00:00')""", (h, doc))


def test_class_distribution_series_aggregates_compose_series_correctly(data_root):
    with conn.session() as cx:
        _seed_multi_series(cx)
        dist = export.class_distribution(cx)
    assert dist["total"] == 4
    # compose_series('TSIII','SA')->'TSIII SA' 2건, compose_series('SSII',None)->'SSII' 1건,
    # compose_series('TSIII','RBM')->'TSIII RBM' 1건. 정렬은 (-count, name).
    assert dist["series"] == [
        {"name": "TSIII SA", "count": 2},
        {"name": "SSII", "count": 1},
        {"name": "TSIII RBM", "count": 1},
    ]
