"""SQLite 커넥션 — WAL 모드, 멱등 마이그레이션.

Dagster 수집 잡과 UI 서버 두 프로세스가 같은 파일을 쓴다. WAL + busy_timeout 으로
동시 접근을 견딘다(쓰기는 짧은 트랜잭션만).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from drheri_pipeline import storage

SCHEMA = Path(__file__).with_name("schema.sql")


def db_path() -> Path:
    p = storage.DATA_ROOT / "pipeline.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect() -> sqlite3.Connection:
    cx = sqlite3.connect(db_path(), timeout=30, isolation_level=None)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("PRAGMA foreign_keys=ON")
    cx.execute("PRAGMA busy_timeout=30000")
    return cx


_NEW_IMAGE_COLS = {
    "is_fixture": "INTEGER",
    "diameter": "TEXT",
    "diameter_src": "TEXT",
    "length": "TEXT",
    "length_src": "TEXT",
    "part_number": "TEXT",
    "part_number_src": "TEXT",
    "needs_review": "INTEGER NOT NULL DEFAULT 0",
}


def migrate() -> None:
    """schema.sql(멱등 CREATE) 실행 후, 기존 image 테이블에 없는 새 컬럼을 ALTER 로 채운다."""
    cx = connect()
    try:
        cx.executescript(SCHEMA.read_text(encoding="utf-8"))
        have = {r["name"] for r in cx.execute("PRAGMA table_info(image)").fetchall()}
        for col, decl in _NEW_IMAGE_COLS.items():
            if col not in have:
                cx.execute(f"ALTER TABLE image ADD COLUMN {col} {decl}")
    finally:
        cx.close()


@contextmanager
def session():
    """트랜잭션 세션 — 정상 종료 시 커밋, 예외 시 롤백."""
    cx = connect()
    try:
        cx.execute("BEGIN")
        yield cx
        cx.execute("COMMIT")
    except Exception:
        cx.execute("ROLLBACK")
        raise
    finally:
        cx.close()
