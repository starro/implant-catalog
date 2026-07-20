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


def migrate() -> None:
    """schema.sql 을 그대로 실행. 전부 IF NOT EXISTS 라 멱등."""
    cx = connect()
    try:
        cx.executescript(SCHEMA.read_text(encoding="utf-8"))
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
