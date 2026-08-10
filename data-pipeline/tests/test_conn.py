from drheri_pipeline.db import conn


def test_migrate_creates_all_tables(data_root):
    with conn.session() as cx:
        rows = cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r["name"] for r in rows}
    assert {"brand", "document", "run", "image", "image_origin", "sync_log"} <= names


def test_migrate_is_idempotent(data_root):
    # 처음 migrate 실행
    conn.migrate()

    # brand 테이블에 테스트 데이터 INSERT
    with conn.session() as cx:
        cx.execute(
            "INSERT INTO brand (name_norm, name_raw, created_at) VALUES (?, ?, ?)",
            ("OSSTEM IMPLANT", "Osstem", "2025-07-20T12:00:00Z")
        )

    # 두 번째 migrate 실행 (멱등성 검증)
    conn.migrate()

    # 데이터가 그대로 남아있는지 확인
    with conn.session() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM brand").fetchone()["c"]
        assert n == 1, "멱등 마이그레이션 후 행 개수가 1이어야 함"

        # 데이터 내용이 동일한지 확인
        brand = cx.execute("SELECT name_norm FROM brand WHERE id = 1").fetchone()
        assert brand["name_norm"] == "OSSTEM IMPLANT", "데이터가 변경되지 않아야 함"


def test_wal_and_foreign_keys_enabled(data_root):
    with conn.session() as cx:
        assert cx.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert cx.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrate_adds_new_image_columns(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    conn.migrate()
    conn.migrate()   # 멱등 — 두 번 호출해도 예외 없음
    cx = conn.connect()
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(image)").fetchall()}
    cx.close()
    assert {"is_fixture", "diameter", "diameter_src", "needs_review"} <= cols


def test_migrate_alters_existing_table_missing_new_columns(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    # 새 4컬럼이 없는 '옛' image 테이블을 먼저 만든다(기존 DB 흉내) — schema.sql 의 image CREATE 에서
    # is_fixture/diameter/diameter_src/needs_review 4줄만 뺀 것과 동일한 컬럼 집합.
    cx = conn.connect()
    cx.execute("""CREATE TABLE image (
        content_hash TEXT PRIMARY KEY, ext TEXT NOT NULL DEFAULT 'png',
        width INTEGER, height INTEGER, brand TEXT, series TEXT, surface TEXT, model TEXT,
        modality TEXT, review_state TEXT NOT NULL DEFAULT 'pending', reject_reason TEXT,
        reviewed_at TEXT, stage TEXT NOT NULL DEFAULT 'review', rel_path TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    cx.close()
    conn.migrate()      # 이제 executescript 는 CREATE IF NOT EXISTS 로 no-op, ALTER 가 4컬럼을 채운다
    cx = conn.connect()
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(image)").fetchall()}
    cx.close()
    assert {"is_fixture", "diameter", "diameter_src", "needs_review"} <= cols
