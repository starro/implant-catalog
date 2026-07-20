"""manifest.jsonl / sources.jsonl → SQLite 최초 백필 (멱등).

실행: DATA_ROOT=/path/to/data .venv/Scripts/python -m scripts.backfill_db
"""
from __future__ import annotations

import json

from drheri_pipeline import storage
from drheri_pipeline.db import conn, writes

_TABLES = ("brand", "document", "run", "image", "image_origin")


def _doc_url(origin_url: str | None) -> str:
    return (origin_url or "").split("#page=")[0].strip()


def _read_sources() -> list[dict]:
    p = storage.DATA_ROOT / "sources.jsonl"
    if not p.exists():
        return []
    latest: dict[str, dict] = {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                latest[r["id"]] = r          # append-only — 뒤가 최신
    return list(latest.values())


def _ensure_document(cx, url: str, brand: str, entry: dict | None) -> int:
    row = cx.execute("SELECT id FROM document WHERE url=?", (url,)).fetchone()
    if row:
        return row["id"]
    e = entry or {}
    return writes.create_document(
        cx, brand_raw=brand or "_unknown", name=url.rsplit("/", 1)[-1] or url, url=url,
        source_type="catalog_pdf",
        default_conf=float(e.get("conf") or 0.35),
        default_dpi=int(e.get("dpi") or 200),
        default_pages=e.get("pages") or "",
        default_series=e.get("series") or "_unknown",
        memo="")


def _counts(cx) -> dict:
    return {t: cx.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in _TABLES}


def backfill() -> dict:
    conn.migrate()
    manifest = storage.latest_by_hash()          # content_hash 별 최신 레코드
    sources = _read_sources()

    with conn.session() as cx:
        before = _counts(cx)

        # 1) sources.jsonl → document + run
        for s in sources:
            url = (s.get("url") or "").strip()
            if not url:
                continue
            doc_id = _ensure_document(cx, url, s.get("brand") or "Osstem", s)
            dup = cx.execute("SELECT id FROM run WHERE document_id=? AND started_at=?",
                             (doc_id, s.get("created_at") or "")).fetchone()
            if dup:
                continue
            cx.execute(
                """INSERT INTO run (document_id, dagster_run_id, conf, dpi, pages,
                                    status, extracted, started_at, finished_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (doc_id, s.get("run_id"), float(s.get("conf") or 0.35),
                 int(s.get("dpi") or 200), s.get("pages") or "",
                 s.get("status") or "SUCCESS", int(s.get("figures") or 0),
                 s.get("created_at") or "", s.get("updated_at")))

        # 2) manifest → image + image_origin
        for rec in manifest.values():
            url = _doc_url(rec.get("origin_url"))
            if not url:
                continue
            doc_id = _ensure_document(cx, url, rec.get("brand") or "_unknown", None)
            writes.record_image(cx, rec, doc_id, None)
            if rec.get("stage") == "training":
                cx.execute(
                    """UPDATE image SET stage='training', review_state='kept',
                       reviewed_at=COALESCE(reviewed_at, ?) WHERE content_hash=?""",
                    (rec.get("approved_at") or rec.get("fetched_at"), rec["content_hash"]))

        after = _counts(cx)

    return {"brands": after["brand"] - before["brand"],
            "documents": after["document"] - before["document"],
            "runs": after["run"] - before["run"],
            "images": after["image"] - before["image"],
            "origins": after["image_origin"] - before["image_origin"]}


if __name__ == "__main__":
    print(backfill())
