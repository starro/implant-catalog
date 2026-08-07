import pytest
from drheri_pipeline.labeling import fiftyone_writer

fo = pytest.importorskip("fiftyone")


def test_register_prelabeled_sets_fields_and_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(fiftyone_writer.storage, "DATA_ROOT", tmp_path)
    img = tmp_path / "crop.png"
    from PIL import Image; Image.new("RGB", (10, 10)).save(img)
    ds_name = "drheri_test_prelabel"
    monkeypatch.setattr(fiftyone_writer, "DATASET", ds_name)
    if ds_name in fo.list_datasets():
        fo.delete_dataset(ds_name)
    rec = {"content_hash": "h1", "path": "crop.png", "brand": "BEGO", "model": "SC",
           "diameter": "4.1", "length": None, "part_number": "58160",
           "ai_confidence": 0.4, "evidence": "SC", "source_page": 18,
           "bbox": [1, 2, 3, 4], "needs_review": True}
    n = fiftyone_writer.register_prelabeled([rec])
    assert n == 1
    ds = fo.load_dataset(ds_name)
    s = next(iter(ds))
    assert s["brand"] == "BEGO" and s["model"] == "SC" and s["diameter"] == "4.1"
    assert "needs_review" in s.tags
    # 멱등: 같은 hash 재등록은 0
    assert fiftyone_writer.register_prelabeled([rec]) == 0
    fo.delete_dataset(ds_name)


def test_register_prelabeled_dedups_within_same_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(fiftyone_writer.storage, "DATA_ROOT", tmp_path)
    img = tmp_path / "crop.png"
    from PIL import Image; Image.new("RGB", (10, 10)).save(img)
    ds_name = "drheri_test_prelabel_batch_dedup"
    monkeypatch.setattr(fiftyone_writer, "DATASET", ds_name)
    if ds_name in fo.list_datasets():
        fo.delete_dataset(ds_name)
    rec = {"content_hash": "h1", "path": "crop.png", "brand": "BEGO", "model": "SC",
           "diameter": "4.1", "length": None, "part_number": "58160",
           "ai_confidence": 0.4, "evidence": "SC", "source_page": 18,
           "bbox": [1, 2, 3, 4], "needs_review": True}
    # 같은 content_hash 를 가진 두 레코드를 한 배치로 등록 — 하나만 추가되어야 함
    n = fiftyone_writer.register_prelabeled([rec, dict(rec)])
    assert n == 1
    fo.delete_dataset(ds_name)
