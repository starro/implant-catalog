from drheri_pipeline.db import conn


def test_migrate_creates_all_tables(data_root):
    with conn.session() as cx:
        rows = cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r["name"] for r in rows}
    assert {"brand", "document", "run", "image", "image_origin", "sync_log"} <= names


def test_migrate_is_idempotent(data_root):
    conn.migrate()
    conn.migrate()
    with conn.session() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM brand").fetchone()["c"]
    assert n == 0


def test_wal_and_foreign_keys_enabled(data_root):
    with conn.session() as cx:
        assert cx.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert cx.execute("PRAGMA foreign_keys").fetchone()[0] == 1
