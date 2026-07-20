"""운영 DB 읽기 — 퍼널 집계와 화면용 조회.

퍼널 정의(스펙 §5.1):
  추출 = 해당 문서의 image_origin 행 수
  학습 = 그중 stage='training'
  버림 = 그중 review_state='rejected'
  대기 = 추출 - 학습 - 버림   (뺄셈 정의 — 어느 칸에도 안 잡히는 건이 생기지 않게)
"""
from __future__ import annotations

import sqlite3

_FUNNEL_SELECT = """
  COUNT(*)                                                     AS extracted,
  SUM(CASE WHEN i.stage='training'        THEN 1 ELSE 0 END)   AS training,
  SUM(CASE WHEN i.review_state='rejected' THEN 1 ELSE 0 END)   AS rejected,
  SUM(CASE WHEN i.review_state='pending'  THEN 1 ELSE 0 END)   AS unreviewed,
  SUM(CASE WHEN i.review_state='kept' AND i.stage<>'training'
                                          THEN 1 ELSE 0 END)   AS label_incomplete
"""

EMPTY_FUNNEL = {"extracted": 0, "training": 0, "rejected": 0,
                "pending": 0, "unreviewed": 0, "label_incomplete": 0}


def _funnel(row: sqlite3.Row | None) -> dict:
    if row is None or not row["extracted"]:
        return dict(EMPTY_FUNNEL)
    extracted = row["extracted"] or 0
    training = row["training"] or 0
    rejected = row["rejected"] or 0
    return {
        "extracted": extracted,
        "training": training,
        "rejected": rejected,
        "pending": extracted - training - rejected,
        "unreviewed": row["unreviewed"] or 0,
        "label_incomplete": row["label_incomplete"] or 0,
    }


def funnel_for_document(cx: sqlite3.Connection, doc_id: int) -> dict:
    row = cx.execute(
        f"""SELECT {_FUNNEL_SELECT}
            FROM image_origin o JOIN image i ON i.content_hash = o.content_hash
            WHERE o.document_id = ?""", (doc_id,)).fetchone()
    return _funnel(row)


def _add(a: dict, b: dict) -> dict:
    return {k: a[k] + b[k] for k in a}


def source_tree(cx: sqlite3.Connection) -> list[dict]:
    """브랜드 › 문서 트리. 보관(archived) 문서는 제외한다."""
    docs = cx.execute(
        """SELECT d.id, d.name, d.url, d.source_type,
                  b.id AS brand_id, b.name_norm AS brand,
                  (SELECT started_at FROM run r WHERE r.document_id=d.id
                    ORDER BY r.started_at DESC LIMIT 1) AS last_run_at,
                  (SELECT status FROM run r WHERE r.document_id=d.id
                    ORDER BY r.started_at DESC LIMIT 1) AS last_run_status
           FROM document d JOIN brand b ON b.id = d.brand_id
           WHERE d.status = 'active'
           ORDER BY b.name_norm, d.name""").fetchall()

    groups: dict[int, dict] = {}
    order: list[int] = []
    for d in docs:
        if d["brand_id"] not in groups:
            groups[d["brand_id"]] = {"brand_id": d["brand_id"], "brand": d["brand"],
                                     "funnel": dict(EMPTY_FUNNEL), "documents": []}
            order.append(d["brand_id"])
        g = groups[d["brand_id"]]
        f = funnel_for_document(cx, d["id"])
        g["documents"].append({
            "id": d["id"], "name": d["name"], "url": d["url"],
            "source_type": d["source_type"], "funnel": f,
            "last_run_at": d["last_run_at"], "last_run_status": d["last_run_status"]})
        g["funnel"] = _add(g["funnel"], f)
    return [groups[i] for i in order]


def document_detail(cx: sqlite3.Connection, doc_id: int) -> dict | None:
    d = cx.execute(
        """SELECT d.*, b.name_norm AS brand, b.name_raw AS brand_raw
           FROM document d JOIN brand b ON b.id = d.brand_id WHERE d.id = ?""",
        (doc_id,)).fetchone()
    if d is None:
        return None
    runs = cx.execute(
        """SELECT id, dagster_run_id, conf, dpi, pages, status, extracted,
                  started_at, finished_at, error
           FROM run WHERE document_id = ? ORDER BY started_at DESC""", (doc_id,)).fetchall()
    return {**dict(d), "funnel": funnel_for_document(cx, doc_id),
            "runs": [dict(r) for r in runs]}


def overview(cx: sqlite3.Connection) -> dict:
    row = cx.execute(
        f"""SELECT {_FUNNEL_SELECT}
            FROM image_origin o JOIN image i ON i.content_hash = o.content_hash""").fetchone()
    runs = cx.execute(
        """SELECT r.id, r.status, r.extracted, r.started_at, r.finished_at,
                  d.id AS document_id, d.name AS document_name
           FROM run r JOIN document d ON d.id = r.document_id
           ORDER BY r.started_at DESC LIMIT 20""").fetchall()
    return {"funnel": _funnel(row), "recent_runs": [dict(r) for r in runs]}


def find_document_by_url(cx: sqlite3.Connection, url: str) -> dict | None:
    row = cx.execute(
        """SELECT d.id, d.name, d.status, b.name_norm AS brand
           FROM document d JOIN brand b ON b.id = d.brand_id WHERE d.url = ?""",
        ((url or "").strip(),)).fetchone()
    return dict(row) if row else None


def running_runs(cx: sqlite3.Connection) -> list[dict]:
    rows = cx.execute(
        """SELECT id, document_id, dagster_run_id, started_at
           FROM run WHERE status IN ('QUEUED','RUNNING')""").fetchall()
    return [dict(r) for r in rows]
