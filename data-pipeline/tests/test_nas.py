import pytest

from drheri_pipeline.ui.api import nas
from drheri_pipeline.ui.envelope import ApiError


def _seed(root):
    (root / "ADIN").mkdir()
    (root / "ADIN" / "manual.pdf").write_bytes(b"%PDF-1.4 x")
    (root / "ADIN" / "notes.txt").write_text("skip me")   # PDF 아닌 건 목록 제외
    (root / "BEGO").mkdir()
    (root / ".hidden").mkdir()                             # 숨김 폴더 제외


def test_browse_lists_brand_dirs(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NAS_CATALOG_ROOT", str(tmp_path))
    r = nas._browse("")
    assert r["available"] is True
    assert [d["name"] for d in r["dirs"]] == ["ADIN", "BEGO"]   # 정렬 + 숨김 제외
    assert r["files"] == []


def test_browse_lists_only_pdfs_with_abs(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NAS_CATALOG_ROOT", str(tmp_path))
    r = nas._browse("ADIN")
    names = [f["name"] for f in r["files"]]
    assert names == ["manual.pdf"]                          # notes.txt 제외
    assert r["files"][0]["abs"].endswith("manual.pdf")
    assert r["files"][0]["size"] > 0


def test_browse_rejects_traversal(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("NAS_CATALOG_ROOT", str(tmp_path))
    with pytest.raises(ApiError) as ei:
        nas._browse("../../etc")
    assert ei.value.status == 403


def test_browse_unavailable_when_root_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("NAS_CATALOG_ROOT", str(tmp_path / "nope"))
    r = nas._browse("")
    assert r["available"] is False
    assert r["dirs"] == [] and r["files"] == []
