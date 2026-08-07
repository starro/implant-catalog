import fitz
from PIL import Image
from drheri_pipeline.labeling import runner
from drheri_pipeline.labeling.detect import Box
from drheri_pipeline.labeling.mapper import BoxSpec


def _pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        doc.new_page(width=595, height=842).insert_text((72, 72), f"REF 5816{i}")
    doc.save(str(path)); doc.close()


def test_label_catalog_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(runner.storage, "MANIFEST", tmp_path / "manifest.jsonl")
    pdf = tmp_path / "c.pdf"; _pdf(pdf, pages=2)

    # 페이지1: 박스 1개 / 페이지2: 박스 0개(필터로 스킵)
    calls = {"n": 0}
    def fake_detect(image, **kw):
        calls["n"] += 1
        return [Box(0.5, (1, 1, 5, 5))] if calls["n"] == 1 else []
    monkeypatch.setattr(runner, "detect_fixtures", fake_detect)
    monkeypatch.setattr(runner, "map_specs", lambda *a, **k: [
        BoxSpec(0, "SC", "4.1", None, "58160", 0.9, "SC 4.1")])
    written = {"recs": None}
    monkeypatch.setattr(runner, "register_prelabeled",
                        lambda recs, log=print: written.__setitem__("recs", recs) or len(recs))

    summ = runner.label_catalog(str(pdf), "BEGO", max_workers=1)
    assert summ.fixture_pages == 1 and summ.crops == 1
    assert written["recs"][0]["brand"] == "BEGO" and written["recs"][0]["model"] == "SC"
    # 크롭 파일·manifest 기록됨
    assert (tmp_path / "manifest.jsonl").exists()
    assert written["recs"][0]["source_pdf"] == str(pdf)
    assert written["recs"][0]["origin_url"].endswith("#page=1")


def test_needs_review_when_confidence_low(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(runner.storage, "MANIFEST", tmp_path / "m.jsonl")
    pdf = tmp_path / "c.pdf"; _pdf(pdf, pages=1)
    monkeypatch.setattr(runner, "detect_fixtures", lambda v, **k: [Box(0.5, (1, 1, 5, 5))])
    monkeypatch.setattr(runner, "map_specs", lambda *a, **k: [
        BoxSpec(0, None, None, None, None, 0.2, "")])   # 저confidence + 필드 누락
    monkeypatch.setattr(runner, "register_prelabeled", lambda recs, log=print: len(recs))
    summ = runner.label_catalog(str(pdf), "BEGO", max_workers=1)
    assert summ.needs_review == 1
