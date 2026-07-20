import json

from drheri_pipeline import storage
from drheri_pipeline.db import conn
from scripts import backfill_db


def _write_fixtures(root):
    manifest = [
        {"content_hash": "h1", "path": "review/a/h1.png", "stage": "review",
         "brand": "Osstem", "series": "_unknown", "model": "_unknown",
         "modality": "catalog", "origin_url": "https://ex.com/a.pdf#page=3",
         "page_no": 3, "bbox": [1, 2, 3, 4], "fetched_at": "2026-07-06T05:43:00+00:00"},
        {"content_hash": "h2", "path": "training/a/h2.png", "stage": "training",
         "brand": "Osstem", "series": "TSIII", "model": "TSIII4010S",
         "modality": "catalog", "origin_url": "https://ex.com/a.pdf#page=4",
         "page_no": 4, "bbox": [5, 6, 7, 8], "approved_at": "2026-07-07T00:00:00+00:00"},
    ]
    (root / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r) for r in manifest) + "\n", encoding="utf-8")
    sources = [{"id": "s1", "url": "https://ex.com/a.pdf", "brand": "Osstem",
                "conf": 0.35, "dpi": 200, "pages": "", "status": "SUCCESS",
                "figures": 2, "created_at": "2026-07-06T05:43:00+00:00"}]
    (root / "sources.jsonl").write_text(
        "\n".join(json.dumps(r) for r in sources) + "\n", encoding="utf-8")


def test_backfill_imports_everything(data_root):
    _write_fixtures(storage.DATA_ROOT)
    stats = backfill_db.backfill()
    assert stats["documents"] == 1
    assert stats["images"] == 2
    with conn.session() as cx:
        img = cx.execute("SELECT * FROM image WHERE content_hash='h2'").fetchone()
    assert img["stage"] == "training"
    assert img["review_state"] == "kept"       # training 이었으면 이미 승인된 것


def test_backfill_is_idempotent(data_root):
    _write_fixtures(storage.DATA_ROOT)
    backfill_db.backfill()
    backfill_db.backfill()
    with conn.session() as cx:
        counts = {t: cx.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                  for t in ("brand", "document", "run", "image", "image_origin")}
    assert counts == {"brand": 1, "document": 1, "run": 1, "image": 2, "image_origin": 2}


def test_backfill_dedup_prefers_dagster_run_id_over_started_at(data_root):
    """추가 항목: sources.jsonl 에 created_at 이 없거나 겹쳐도, dagster_run_id(run_id) 가 있으면
    그걸 중복 판정 키로 써야 서로 다른 수집이 하나로 합쳐지지 않는다. run_id 가 있는 한
    멱등성(재실행해도 부풀지 않음)은 그대로 유지돼야 한다."""
    sources = [
        {"id": "s1a", "url": "https://ex.com/a.pdf", "brand": "Osstem",
         "conf": 0.35, "dpi": 200, "pages": "", "status": "SUCCESS",
         "figures": 2, "run_id": "dagster-run-A"},                      # created_at 없음
        {"id": "s1b", "url": "https://ex.com/a.pdf", "brand": "Osstem",
         "conf": 0.35, "dpi": 200, "pages": "", "status": "SUCCESS",
         "figures": 3, "run_id": "dagster-run-B"},                      # 같은 문서, 다른 런, created_at 없음
    ]
    (storage.DATA_ROOT / "sources.jsonl").write_text(
        "\n".join(json.dumps(r) for r in sources) + "\n", encoding="utf-8")

    stats = backfill_db.backfill()
    assert stats["documents"] == 1        # 같은 url → 문서는 하나
    assert stats["runs"] == 2             # run_id 가 다르므로 런은 병합되지 않고 둘 다 생성

    # 재실행해도 멱등 — 같은 run_id 재등장은 중복으로 걸러진다
    stats2 = backfill_db.backfill()
    assert stats2["runs"] == 0
    with conn.session() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM run").fetchone()["c"]
    assert n == 2
