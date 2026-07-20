from pathlib import Path

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


def _seed_four_images(data_root):
    """kept/rejected/promoted 가 서로 다른 값이 되도록 이미지 4장을 시딩."""
    with conn.session() as cx:
        doc = writes.create_document(
            cx, brand_raw="Osstem", name="TS", url="https://ex.com/four.pdf",
            source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
            default_pages="", default_series="_unknown", memo="")
        for h in ("k1", "k2", "k3", "r1"):
            p = storage.DATA_ROOT / "review" / f"{h}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"png")
            writes.record_image(cx, {
                "content_hash": h, "path": f"review/{h}.png", "brand": "Osstem",
                "series": "_unknown", "surface": None, "model": "_unknown",
                "modality": "catalog", "page_no": 1, "bbox": [0, 0, 1, 1]}, doc, None)
    return doc


def test_sync_log_db_values_match_kept_rejected_promoted_distinctly(data_root, monkeypatch):
    """반환 dict 만이 아니라 DB 에 실제로 기록된 UPDATE 인자 순서/값을 검증한다.

    kept=3, rejected=1, promoted=2 로 세 값을 모두 다르게 만들어, kept/rejected/promoted 인자가
    뒤바뀌어 들어가도 (예: kept 자리에 rejected 값) 반드시 걸리도록 한다.
    """
    _seed_four_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "k1", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": "SA", "model": "TSIII4010S"},
        {"content_hash": "k2", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": "SA", "model": "TSIII4010S"},
        {"content_hash": "k3", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": None, "model": "_unknown"},  # 라벨 불완전 → 승급 제외
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"},
    ])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)

    out = sync.run_sync()
    assert (out["kept"], out["rejected"], out["promoted"]) == (3, 1, 2)

    with conn.session() as cx:
        row = cx.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row["kept"] == 3
    assert row["rejected"] == 1
    assert row["promoted"] == 2


def test_stale_fiftyone_filepath_is_retried_on_next_sync(data_root, monkeypatch):
    """A: 이전 동기화에서 FiftyOne 반영이 실패해 filepath 가 옛 경로를 가리키는 상황을 재현.

    이번 sync 에서 태그/라벨은 그대로(변경 없음)라 DB 상 새로 "옮길 것"은 없지만,
    DB rel_path 와 FiftyOne 의 filepath 가 여전히 다르므로 재시도 대상으로 다시 잡혀야 한다.
    """
    doc = _seed_images(data_root)
    with conn.session() as cx:
        cx.execute("""UPDATE image SET stage='training', review_state='kept',
                      brand='OSSTEM IMPLANT', series='TSIII', surface='SA', model='TSIII4010S'
                      WHERE content_hash='k1'""")
    # 실제 파일은 이미 옮겨진 상태로 시뮬레이션 (2단계는 이미 완료됐던 것으로 가정)
    dst = storage.stage_image_path("training", "OSSTEM IMPLANT", "TSIII", "TSIII4010S", "catalog", "k1", "png")
    (storage.DATA_ROOT / "review" / "k1.png").rename(dst)
    with conn.session() as cx:
        cx.execute("UPDATE image SET rel_path=? WHERE content_hash='k1'", (storage.rel(dst),))

    stale_filepath = str((storage.DATA_ROOT / "review" / "k1.png").resolve())
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "k1", "tags": [], "brand": "Osstem", "series": "TSIII",
         "surface": "SA", "model": "TSIII4010S", "filepath": stale_filepath, "stage": "review"}])

    captured = {}

    def fake_push(moves):
        captured.update(moves)
        return 0

    monkeypatch.setattr(sync, "push_stage_to_fiftyone", fake_push)

    sync.run_sync()

    assert "k1" in captured
    pushed_path, pushed_stage = captured["k1"]
    assert pushed_stage == "training"
    assert Path(pushed_path) == dst.resolve()


def test_un_reject_returns_stage_to_review_and_moves_file_back(data_root, monkeypatch):
    """B: 버림 → keep 오판 복구인데 라벨이 아직 불완전하면 review 로 되돌아가야 한다(영구 rejected 방지)."""
    _seed_images(data_root)

    # 1차: r1 버림 처리
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"}])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)
    sync.run_sync()

    with conn.session() as cx:
        row = cx.execute("SELECT * FROM image WHERE content_hash='r1'").fetchone()
    assert row["stage"] == "rejected"
    assert (storage.DATA_ROOT / "rejected" / "r1.png").exists()

    # 2차: FiftyOne 에서 keep 으로 오판 복구했지만 라벨은 여전히 불완전
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "r1", "tags": ["keep"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"}])
    sync.run_sync()

    with conn.session() as cx:
        row = cx.execute("SELECT * FROM image WHERE content_hash='r1'").fetchone()
    assert row["stage"] == "review"
    assert row["review_state"] == "kept"
    assert row["rel_path"].startswith("review/")
    assert (storage.DATA_ROOT / row["rel_path"]).exists()
    assert not (storage.DATA_ROOT / "rejected" / "r1.png").exists()
