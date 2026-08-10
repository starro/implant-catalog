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
