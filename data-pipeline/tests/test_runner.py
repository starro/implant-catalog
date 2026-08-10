import fitz
from PIL import Image
from drheri_pipeline.labeling import runner
from drheri_pipeline.labeling.detect import Box
from drheri_pipeline.labeling.mapper import BoxSpec
from drheri_pipeline.labeling.crop_judge import FixtureJudge
from drheri_pipeline.labeling.spec_mark import MarkSpec


def _pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        doc.new_page(width=595, height=842).insert_text((72, 72), f"REF 5816{i}")
    doc.save(str(path)); doc.close()


def test_label_catalog_end_to_end(tmp_path, monkeypatch):
    # 기본(crop) 경로: is_fixture=judge_fixtures, model=페이지 제목(model_from_heading)
    monkeypatch.setattr(runner.storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(runner.storage, "MANIFEST", tmp_path / "manifest.jsonl")
    pdf = tmp_path / "c.pdf"; _pdf(pdf, pages=2)

    # 페이지1: 박스 1개 / 페이지2: 박스 0개(필터로 스킵)
    calls = {"n": 0}
    def fake_detect(image, **kw):
        calls["n"] += 1
        return [Box(0.5, (1, 1, 5, 5))] if calls["n"] == 1 else []
    monkeypatch.setattr(runner, "JUDGE_MODE", "crop")
    monkeypatch.setattr(runner, "detect_fixtures", fake_detect)
    monkeypatch.setattr(runner, "judge_fixtures", lambda *a, **k: [FixtureJudge(True, 0.9, "ok")])
    monkeypatch.setattr(runner, "MODEL_FROM_HEADING", True)   # 배선 확인용(기본은 꺼짐)
    monkeypatch.setattr(runner, "model_from_heading", lambda *a, **k: "SC")
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
    monkeypatch.setattr(runner, "JUDGE_MODE", "crop")
    monkeypatch.setattr(runner, "detect_fixtures", lambda v, **k: [Box(0.5, (1, 1, 5, 5))])
    monkeypatch.setattr(runner, "judge_fixtures", lambda *a, **k: [FixtureJudge(True, 0.2, "")])
    monkeypatch.setattr(runner, "model_from_heading", lambda *a, **k: "SC")
    monkeypatch.setattr(runner, "register_prelabeled", lambda recs, log=print: len(recs))
    summ = runner.label_catalog(str(pdf), "BEGO", max_workers=1)
    assert summ.needs_review == 1


def test_not_fixture_forces_needs_review(tmp_path, monkeypatch):
    # is_fixture=False 면 신뢰도 높아도 needs_review (버리진 않고 검수로 발라냄)
    monkeypatch.setattr(runner.storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(runner.storage, "MANIFEST", tmp_path / "m.jsonl")
    pdf = tmp_path / "c.pdf"; _pdf(pdf, pages=1)
    monkeypatch.setattr(runner, "JUDGE_MODE", "crop")
    monkeypatch.setattr(runner, "detect_fixtures", lambda v, **k: [Box(0.5, (1, 1, 5, 5))])
    monkeypatch.setattr(runner, "judge_fixtures", lambda *a, **k: [FixtureJudge(False, 0.95, "ok")])
    monkeypatch.setattr(runner, "model_from_heading", lambda *a, **k: "SC")
    written = {"recs": None}
    monkeypatch.setattr(runner, "register_prelabeled",
                        lambda recs, log=print: written.__setitem__("recs", recs) or len(recs))
    summ = runner.label_catalog(str(pdf), "BEGO", max_workers=1)
    assert summ.needs_review == 1 and written["recs"][0]["is_fixture"] is False


def test_mark_mode_fills_specs_from_vlm(tmp_path, monkeypatch):
    # 기본(mark) 경로: 단일마크 VLM 이 is_fixture+모델+지름+길이+코드를 모두 채운다
    monkeypatch.setattr(runner.storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(runner.storage, "MANIFEST", tmp_path / "m.jsonl")
    pdf = tmp_path / "c.pdf"; _pdf(pdf, pages=1)
    monkeypatch.setattr(runner, "detect_fixtures", lambda v, **k: [Box(0.5, (1, 1, 5, 5))])
    monkeypatch.setattr(runner, "spec_for_boxes", lambda *a, **k: [
        MarkSpec(True, "ETIII NH", "4.5", "7", "ET3R4507B", 0.9, "")])
    written = {"recs": None}
    monkeypatch.setattr(runner, "register_prelabeled",
                        lambda recs, log=print: written.__setitem__("recs", recs) or len(recs))
    summ = runner.label_catalog(str(pdf), "Hiossen", max_workers=1)
    r = written["recs"][0]
    assert summ.crops == 1
    assert r["model"] == "ETIII NH" and r["diameter"] == "4.5" and r["length"] == "7"
    assert r["part_number"] == "ET3R4507B" and r["diameter_src"] == "vlm_mark"
    assert r["is_fixture"] is True


def test_som_mode_uses_map_specs(tmp_path, monkeypatch):
    # 되돌리기 스위치: JUDGE_MODE="som" 이면 예전 set-of-mark(map_specs)로 동작
    monkeypatch.setattr(runner, "JUDGE_MODE", "som")
    monkeypatch.setattr(runner.storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(runner.storage, "MANIFEST", tmp_path / "m.jsonl")
    pdf = tmp_path / "c.pdf"; _pdf(pdf, pages=1)
    monkeypatch.setattr(runner, "detect_fixtures", lambda v, **k: [Box(0.5, (1, 1, 5, 5))])
    monkeypatch.setattr(runner, "map_specs", lambda *a, **k: [
        BoxSpec(0, "SC", "4.1", None, "58160", 0.9, "SC 4.1")])
    written = {"recs": None}
    monkeypatch.setattr(runner, "register_prelabeled",
                        lambda recs, log=print: written.__setitem__("recs", recs) or len(recs))
    summ = runner.label_catalog(str(pdf), "BEGO", max_workers=1)
    assert summ.crops == 1 and written["recs"][0]["model"] == "SC"
