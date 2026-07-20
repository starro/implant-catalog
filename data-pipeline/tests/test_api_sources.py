import pytest
from starlette.testclient import TestClient

from drheri_pipeline.ui import app as ui_app


@pytest.fixture()
def client(data_root):
    return TestClient(ui_app.create_app())


def _create(client, url="https://ex.com/a.pdf", brand="Osstem", name="TS 카탈로그"):
    return client.post("/api/sources", json={
        "url": url, "name": name, "brand": brand,
        "conf": 0.35, "dpi": 200, "pages": "", "series": "_unknown", "memo": "메모"})


def test_create_and_list(client):
    r = _create(client)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    doc_id = r.json()["data"]["id"]

    tree = client.get("/api/sources").json()["data"]
    assert tree[0]["brand"] == "OSSTEM IMPLANT"
    assert tree[0]["documents"][0]["id"] == doc_id
    assert tree[0]["documents"][0]["funnel"]["extracted"] == 0


def test_duplicate_url_returns_409_with_existing_id(client):
    first = _create(client).json()["data"]["id"]
    r = _create(client)
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "duplicate_url"
    assert body["data"] is None

    chk = client.get("/api/sources/check", params={"url": " https://ex.com/a.pdf "}).json()
    assert chk["data"]["exists"] is True
    assert chk["data"]["document"]["id"] == first


def test_check_returns_false_for_new_url(client):
    body = client.get("/api/sources/check", params={"url": "https://ex.com/new.pdf"}).json()
    assert body["data"] == {"exists": False, "document": None}


def test_name_defaults_to_filename(client):
    r = client.post("/api/sources", json={"url": "https://ex.com/ts-gs.pdf", "brand": "Osstem"})
    doc_id = r.json()["data"]["id"]
    detail = client.get(f"/api/sources/{doc_id}").json()["data"]
    assert detail["name"] == "ts-gs.pdf"
    assert detail["default_conf"] == 0.35
    assert detail["default_dpi"] == 200


def test_update_and_archive(client):
    doc_id = _create(client).json()["data"]["id"]
    r = client.post(f"/api/sources/{doc_id}/update",
                    json={"name": "새 이름", "memo": "수정됨", "dpi": 300})
    assert r.json()["ok"] is True
    detail = client.get(f"/api/sources/{doc_id}").json()["data"]
    assert detail["name"] == "새 이름"
    assert detail["default_dpi"] == 300

    client.post(f"/api/sources/{doc_id}/archive")
    assert client.get("/api/sources").json()["data"] == []
    assert client.get(f"/api/sources/{doc_id}").json()["data"]["status"] == "archived"


def test_detail_404_for_missing_document(client):
    r = client.get("/api/sources/9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_create_requires_url(client):
    r = client.post("/api/sources", json={"brand": "Osstem"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"


def test_update_ignores_non_whitelisted_fields(client):
    """update_document 의 화이트리스트(_DOC_EDITABLE)가 API 레벨에서도 유지되는지 확인한다.
    status/id 처럼 화이트리스트 밖 필드는 조용히 무시돼야 하고, name 처럼 화이트리스트 안 필드만 반영돼야 한다."""
    doc_id = _create(client).json()["data"]["id"]
    r = client.post(f"/api/sources/{doc_id}/update",
                    json={"status": "archived", "id": 9999, "bogus_field": "x", "name": "정상 갱신"})
    assert r.json()["ok"] is True

    detail = client.get(f"/api/sources/{doc_id}").json()["data"]
    assert detail["name"] == "정상 갱신"  # 화이트리스트 안 필드는 반영된다
    assert detail["status"] == "active"  # status 는 화이트리스트 밖이므로 무시된다
    assert detail["id"] == doc_id        # id 도 무시된다(원래 id 그대로)
