from drheri_pipeline.db import conn, queries, writes


def _seed(cx):
    doc = writes.create_document(
        cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
        source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
        default_pages="", default_series="_unknown", memo="")
    rows = [
        ("pending", "review", "_unknown"),      # 미검수 → 대기
        ("kept", "review", "_unknown"),         # keep 했지만 라벨 미완 → 대기
        ("kept", "training", "TSIII4010S"),     # 학습
        ("rejected", "rejected", "_unknown"),   # 버림
    ]
    for i, (state, stage, model) in enumerate(rows):
        cx.execute(
            """INSERT INTO image (content_hash, ext, brand, series, model, modality,
                                  review_state, stage, rel_path, created_at)
               VALUES (?,'png','Osstem','TSIII',?,'catalog',?,?,?,'2026-07-20T00:00:00+00:00')""",
            (f"h{i}", model, state, stage, f"review/h{i}.png"))
        cx.execute(
            """INSERT INTO image_origin (content_hash, document_id, created_at)
               VALUES (?,?,'2026-07-20T00:00:00+00:00')""", (f"h{i}", doc))
    return doc


def test_funnel_counts(data_root):
    with conn.session() as cx:
        doc = _seed(cx)
        f = queries.funnel_for_document(cx, doc)
    assert f["extracted"] == 4
    assert f["training"] == 1
    assert f["rejected"] == 1
    assert f["pending"] == 2                 # 추출 - 학습 - 버림
    assert f["unreviewed"] == 1
    assert f["label_incomplete"] == 1


def test_source_tree_rolls_up_to_brand(data_root):
    with conn.session() as cx:
        _seed(cx)
        tree = queries.source_tree(cx)
    assert len(tree) == 1
    assert tree[0]["brand"] == "OSSTEM IMPLANT"
    assert tree[0]["funnel"]["extracted"] == 4
    assert len(tree[0]["documents"]) == 1


def test_archived_document_excluded_from_tree(data_root):
    with conn.session() as cx:
        doc = _seed(cx)
        writes.archive_document(cx, doc)
        tree = queries.source_tree(cx)
    assert tree == []


def test_find_document_by_url(data_root):
    with conn.session() as cx:
        _seed(cx)
        hit = queries.find_document_by_url(cx, " https://ex.com/a.pdf ")
        miss = queries.find_document_by_url(cx, "https://ex.com/zzz.pdf")
    assert hit["name"] == "TS"
    assert miss is None


def test_funnel_counts_needs_review_and_not_fixture(data_root):
    d = None
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u1",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        for h, nf, nr in [("a", True, True), ("b", False, True), ("c", True, False)]:
            writes.record_image(cx, {"content_hash": h, "path": f"{h}.png", "brand": "BEGO",
                                     "is_fixture": nf, "needs_review": nr}, d, None)
        f = queries.funnel_for_document(cx, d)
    assert f["extracted"] == 3 and f["needs_review"] == 2 and f["not_fixture"] == 1
