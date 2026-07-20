import pytest
from starlette.testclient import TestClient

from drheri_pipeline.ui import app as ui_app


@pytest.fixture()
def client(data_root):
    return TestClient(ui_app.create_app())


def test_api_routes_still_work(client):
    assert client.get("/api/health").json()["ok"] is True


def test_root_returns_helpful_message_when_not_built(client, monkeypatch):
    monkeypatch.setattr(ui_app, "DIST", ui_app.DIST.parent / "nonexistent-dist")
    c = TestClient(ui_app.create_app())
    body = c.get("/").json()
    assert body["ok"] is False
    assert "npm run build" in body["error"]["message"]


def test_registry_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import drheri_pipeline.ui.registry  # noqa: F401
