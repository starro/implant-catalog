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
