import pytest
from starlette.testclient import TestClient

from drheri_pipeline import storage
from drheri_pipeline.ui import app as ui_app


@pytest.fixture()
def client(data_root):
    return TestClient(ui_app.create_app())


def _pdf(name="ts-gs.pdf", body=b"%PDF-1.4 hello", brand="Osstem"):
    return {"files": {"file": (name, body, "application/pdf")}, "data": {"brand": brand}}


def test_upload_saves_under_normalized_brand_and_returns_abs_path(client):
    r = client.post("/api/uploads", **_pdf())
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["brand"] == "OSSTEM IMPLANT"
    assert data["filename"] == "ts-gs.pdf"

    from pathlib import Path
    p = Path(data["path"])
    assert p.is_absolute()
    assert p.exists()
    # data/catalog/OSSTEM IMPLANT/ts-gs-<sha8>.pdf
    assert p.parent == storage.DATA_ROOT / "catalog" / "OSSTEM IMPLANT"
    assert p.name.startswith("ts-gs-") and p.suffix == ".pdf"


def test_upload_same_file_is_idempotent(client):
    a = client.post("/api/uploads", **_pdf()).json()["data"]["path"]
    b = client.post("/api/uploads", **_pdf()).json()["data"]["path"]
    assert a == b
    catalog = storage.DATA_ROOT / "catalog" / "OSSTEM IMPLANT"
    assert len(list(catalog.glob("*.pdf"))) == 1


def test_upload_rejects_non_pdf(client):
    r = client.post("/api/uploads",
                    files={"file": ("x.png", b"\x89PNG", "image/png")},
                    data={"brand": "Osstem"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_file"


def test_upload_requires_brand(client):
    r = client.post("/api/uploads",
                    files={"file": ("x.pdf", b"%PDF", "application/pdf")},
                    data={"brand": "  "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


def test_upload_rejects_too_large(client):
    from drheri_pipeline.ui.api import uploads
    big = b"%PDF" + b"0" * (uploads.MAX_BYTES + 1)
    r = client.post("/api/uploads",
                    files={"file": ("big.pdf", big, "application/pdf")},
                    data={"brand": "Osstem"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "file_too_large"


def test_upload_filename_cannot_escape_catalog_dir(client):
    r = client.post("/api/uploads",
                    files={"file": ("../../evil.pdf", b"%PDF", "application/pdf")},
                    data={"brand": "Osstem"})
    assert r.status_code == 200
    from pathlib import Path
    p = Path(r.json()["data"]["path"]).resolve()
    catalog = (storage.DATA_ROOT / "catalog").resolve()
    assert str(p).startswith(str(catalog))       # data/catalog 밖으로 못 나감
