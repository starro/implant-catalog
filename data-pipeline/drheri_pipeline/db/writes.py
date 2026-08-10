"""운영 DB 쓰기 — 모든 함수는 커넥션(cx)을 인자로 받아 호출자 트랜잭션에 참여한다."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from drheri_pipeline.taxonomy import normalize_brand


class DuplicateUrl(Exception):
    """이미 등록된 URL."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_brand(cx: sqlite3.Connection, name_raw: str) -> int:
    norm = normalize_brand(name_raw) or "_unknown"
    row = cx.execute("SELECT id FROM brand WHERE name_norm=?", (norm,)).fetchone()
    if row:
        return row["id"]
    cur = cx.execute(
        "INSERT INTO brand (name_norm, name_raw, created_at) VALUES (?,?,?)",
        (norm, (name_raw or "").strip(), _now()),
    )
    return cur.lastrowid


def create_document(cx: sqlite3.Connection, *, brand_raw: str, name: str, url: str,
                    source_type: str, default_conf: float, default_dpi: int,
                    default_pages: str, default_series: str, memo: str) -> int:
    brand_id = upsert_brand(cx, brand_raw)
    now = _now()
    try:
        cur = cx.execute(
            """INSERT INTO document
               (brand_id, name, url, source_type, default_conf, default_dpi,
                default_pages, default_series, memo, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,'active',?,?)""",
            (brand_id, name, url.strip(), source_type, float(default_conf), int(default_dpi),
             default_pages or "", default_series or "_unknown", memo or "", now, now),
        )
    except sqlite3.IntegrityError as e:
        raise DuplicateUrl(url) from e
    return cur.lastrowid


_DOC_EDITABLE = {"name", "memo", "default_conf", "default_dpi", "default_pages", "default_series"}


def update_document(cx: sqlite3.Connection, doc_id: int, **fields) -> None:
    if "brand_raw" in fields:
        fields["brand_id"] = upsert_brand(cx, fields.pop("brand_raw"))
    cols = {k: v for k, v in fields.items() if k in _DOC_EDITABLE or k == "brand_id"}
    if not cols:
        return
    sets = ", ".join(f"{k}=?" for k in cols)
    cx.execute(f"UPDATE document SET {sets}, updated_at=? WHERE id=?",
               (*cols.values(), _now(), doc_id))


def archive_document(cx: sqlite3.Connection, doc_id: int) -> None:
    cx.execute("UPDATE document SET status='archived', updated_at=? WHERE id=?", (_now(), doc_id))


def create_run(cx: sqlite3.Connection, document_id: int, conf: float, dpi: int, pages: str) -> int:
    cur = cx.execute(
        """INSERT INTO run (document_id, conf, dpi, pages, status, started_at)
           VALUES (?,?,?,?, 'QUEUED', ?)""",
        (document_id, float(conf), int(dpi), pages or "", _now()),
    )
    return cur.lastrowid


def attach_dagster_run(cx: sqlite3.Connection, run_id: int, dagster_run_id: str) -> None:
    cx.execute("UPDATE run SET dagster_run_id=?, status='RUNNING' WHERE id=?",
               (dagster_run_id, run_id))


def finish_run(cx: sqlite3.Connection, run_id: int, status: str,
               extracted: int = 0, error: str | None = None) -> None:
    cx.execute("UPDATE run SET status=?, extracted=?, error=?, finished_at=? WHERE id=?",
               (status, int(extracted), error, _now(), run_id))


def reconcile_interrupted_runs(cx: sqlite3.Connection) -> int:
    """서버(uvicorn) 재시작 등으로 소유 프로세스가 사라진 QUEUED/RUNNING 런을
    FAILURE 로 정리한다. extracted 는 건드리지 않는다(그때까지의 값을 보존).
    """
    cur = cx.execute(
        "UPDATE run SET status='FAILURE', error='interrupted (server restart)', finished_at=? "
        "WHERE status IN ('QUEUED','RUNNING')",
        (_now(),),
    )
    return cur.rowcount


def record_image(cx: sqlite3.Connection, rec: dict, document_id: int,
                 run_id: int | None) -> None:
    """수집 레코드 1건을 image + image_origin 에 기록. 재수집해도 부풀지 않는다.

    이미 있는 이미지의 라벨은 덮어쓰지 않는다 — 사람이 검수해 고친 값을 재수집이 되돌리면 안 된다.
    """
    now = _now()
    h = rec["content_hash"]
    ext = (rec.get("path") or "").rsplit(".", 1)[-1] or "png"
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, surface, model, modality,
                              review_state, stage, rel_path, created_at,
                              is_fixture, diameter, diameter_src, needs_review)
           VALUES (?,?,?,?,?,?,?, 'pending', 'review', ?, ?, ?,?,?,?)
           ON CONFLICT(content_hash) DO NOTHING""",
        (h, ext, rec.get("brand"), rec.get("series"), rec.get("surface"),
         rec.get("model"), rec.get("modality"), rec.get("path"), now,
         1 if rec.get("is_fixture") else (0 if rec.get("is_fixture") is False else None),
         rec.get("diameter"), rec.get("diameter_src"),
         1 if rec.get("needs_review") else 0),
    )
    bbox = rec.get("bbox")
    cx.execute(
        """INSERT INTO image_origin (content_hash, document_id, run_id, page_no, bbox, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(content_hash, document_id) DO NOTHING""",
        (h, document_id, run_id, rec.get("page_no"),
         json.dumps(bbox) if bbox is not None else None, now),
    )
