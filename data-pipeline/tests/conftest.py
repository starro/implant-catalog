import os
import tempfile

import pytest


@pytest.fixture()
def data_root(monkeypatch):
    """테스트마다 격리된 DATA_ROOT — storage 모듈이 import 시점에 읽으므로 reload 한다."""
    import importlib

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("DATA_ROOT", tmp)
        import drheri_pipeline.storage as storage
        importlib.reload(storage)
        import drheri_pipeline.db.conn as conn
        importlib.reload(conn)
        conn.migrate()
        yield storage.DATA_ROOT
