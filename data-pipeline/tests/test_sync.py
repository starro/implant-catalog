import sys
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


def test_is_promotable_requires_brand_and_model():
    # series 는 필수 아님 — brand+model 만 완비되면 kept 는 승급 대상
    assert sync.is_promotable({"review_state": "kept", "brand": "Osstem",
                               "model": "TSIII4010S"}) is True
    assert sync.is_promotable({"review_state": "kept", "brand": "Hiossen",
                               "series": "_unknown", "model": "ETIII NH"}) is True
    # model 없으면 제외
    assert sync.is_promotable({"review_state": "kept", "brand": "Osstem",
                               "series": "TSIII", "model": "_unknown"}) is False
    # brand 없으면 제외
    assert sync.is_promotable({"review_state": "kept", "brand": "_unknown",
                               "model": "TSIII4010S"}) is False
    # kept 아니면 제외
    assert sync.is_promotable({"review_state": "pending", "brand": "Osstem",
                               "model": "TSIII4010S"}) is False


def test_run_sync_applies_tags_labels_and_promotion(data_root, monkeypatch):
    doc = _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[
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
                 "unreviewed": 0, "label_incomplete": 1,
                 "needs_review": 0, "not_fixture": 0}
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
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[
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


def test_rejected_sample_is_deleted_from_fiftyone(data_root, monkeypatch):
    """버림 처리된 것은 FiftyOne 에서 실제로 제거돼야 라벨링 뷰에서 사라진다.
    다만 DB 행·rejected/ 파일은 남아 복구 가능(파일 이동은 유지)."""
    _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[
        {"content_hash": "k1", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": "SA", "model": "TSIII4010S"},
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"}])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)
    deleted = {}
    monkeypatch.setattr(sync, "delete_fiftyone_samples",
                        lambda hashes: (deleted.setdefault("hashes", list(hashes)), len(hashes))[1])

    out = sync.run_sync()
    # 버림된 r1 만 FiftyOne 삭제 대상 (keep 한 k1 은 아님)
    assert deleted["hashes"] == ["r1"]
    assert out["fiftyone_deleted"] == 1
    # 파일·DB 는 그대로 (복구 가능)
    with conn.session() as cx:
        row = cx.execute("SELECT * FROM image WHERE content_hash='r1'").fetchone()
    assert row["stage"] == "rejected"
    assert (storage.DATA_ROOT / row["rel_path"]).exists()


def test_sync_log_is_recorded(data_root, monkeypatch):
    _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[])
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
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[
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
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[
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
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"}])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)
    sync.run_sync()

    with conn.session() as cx:
        row = cx.execute("SELECT * FROM image WHERE content_hash='r1'").fetchone()
    assert row["stage"] == "rejected"
    assert (storage.DATA_ROOT / "rejected" / "r1.png").exists()

    # 2차: FiftyOne 에서 keep 으로 오판 복구했지만 라벨은 여전히 불완전
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[
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


class _FakeSample(dict):
    """FiftyOne Sample 을 흉내낸 최소 스텁 — select_fields 로 선택된 필드만 담는다."""

    def __init__(self, data: dict, tags: list[str]):
        super().__init__(data)
        self.tags = tags


class _FakeDataset:
    """FiftyOne Dataset 을 흉내낸 최소 스텁.

    실제 FiftyOne 은 get_field_schema() 에 없는 필드를 select_fields() 로 요청하면 예외를 던진다.
    이 스텁도 동일하게, select_fields 에 넘어온 필드 중 스키마에 있는 것만 샘플에 채워
    "방어 없이 짰다면 KeyError/예외가 났을 것"을 재현한다.
    """

    def __init__(self, schema: dict, samples: list[dict]):
        self._schema = schema
        self._samples = samples

    def get_field_schema(self) -> dict:
        return self._schema

    def select_fields(self, fields: list[str]):
        out = []
        for s in self._samples:
            data = {f: s[f] for f in fields if f in self._schema}
            out.append(_FakeSample(data, s.get("tags", [])))
        return out


class _FakeFiftyOneModule:
    def __init__(self, dataset: "_FakeDataset"):
        self._dataset = dataset

    def list_datasets(self):
        return [sync.DATASET]

    def load_dataset(self, name):
        assert name == sync.DATASET
        return self._dataset


def test_read_review_state_fills_missing_schema_fields_with_none(monkeypatch):
    """Critical 2: surface 필드가 없는(구버전) FiftyOne 데이터셋을 만나도 예외 없이 동작해야 하고,
    없는 필드는 None 으로 채워야 한다. 실제 FiftyOne 없이 sys.modules 에 가짜 모듈을 주입해 검증한다.
    """
    schema = {"content_hash": object(), "filepath": object(), "stage": object(),
              "brand": object(), "series": object(), "model": object()}   # surface 없음(구버전)
    samples = [{"content_hash": "h1", "filepath": "/data/review/h1.png", "stage": "review",
                "brand": "Osstem", "series": "TSIII", "model": "TSIII4010S", "tags": ["keep"]}]
    fake_module = _FakeFiftyOneModule(_FakeDataset(schema, samples))
    monkeypatch.setitem(sys.modules, "fiftyone", fake_module)

    out = sync.read_review_state()

    assert out == [{"content_hash": "h1", "tags": ["keep"], "filepath": "/data/review/h1.png",
                    "stage": "review", "brand": "Osstem", "series": "TSIII",
                    "surface": None, "model": "TSIII4010S",
                    "diameter": None, "length": None, "part_number": None}]


def test_run_sync_succeeds_even_if_saved_views_sync_fails(data_root, monkeypatch):
    """Important 1: FiftyOne saved view 자동 갱신이 실패해도(FiftyOne 미설치 등) run_sync() 는
    정상 결과를 반환해야 한다 — 예외를 밖으로 던지면 안 된다."""
    from scripts import fiftyone_saved_views

    def _boom():
        raise RuntimeError("FiftyOne 연결 실패(테스트)")

    monkeypatch.setattr(fiftyone_saved_views, "sync_views", _boom)
    _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda *a:[])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)

    out = sync.run_sync()

    assert out["kept"] == 0
    assert out["rejected"] == 0
    assert out["saved_views"]["ok"] is False
    assert "FiftyOne 연결 실패" in out["saved_views"]["detail"]
