"""대화형 라벨링 세션 — FiftyOne App + Python 헬퍼.

FiftyOne App 은 '선택(체크박스)'과 'tag'만 제공하고 brand/series/model 같은 필드를
클릭으로 편집하진 못한다 → App에서 선택 후 이 프롬프트의 헬퍼로 라벨을 적용한다.

실행 (본인 터미널, 백그라운드 X):
  scripts/label.ps1            # 또는 bash scripts/label.sh
  (내부적으로  python -i scripts/label_session.py)

App: stage=review + modality=catalog 등으로 필터 → 라벨링할 샘플 체크박스 선택.
프롬프트:
  sel()                                  # 현재 선택 수 확인
  label(series='SSII', model='SS2R4011S')# 선택분에 라벨 적용 (brand/series/model 일부만도 가능)
  keep()                                 # 선택분 keep 표시
  reject()                               # 선택분 reject 표시
  summary()                              # 태그/stage 현황
  promote_keeps()                        # keep 표시분 → training + manifest + labels.tsv
"""
import shutil
from datetime import datetime, timezone

import fiftyone as fo
from fiftyone import ViewField as F

from drheri_pipeline import storage
import fiftyone_review as RV  # build_dataset / build_views (manifest → 데이터셋)

DATASET = "drheri"

ds = RV.build_dataset()
RV.build_views(ds)
session = fo.launch_app(ds, port=5151)


def _sel_view():
    return ds.select(session.selected)


def sel():
    """현재 App 선택 수."""
    v = _sel_view()
    print(f"선택: {len(v)}장")
    return v


def label(brand=None, series=None, model=None):
    """선택분에 라벨 적용 (지정한 것만). FiftyOne 필드 갱신."""
    ids = list(session.selected)
    if not ids:
        print("선택된 샘플이 없습니다. App 에서 체크박스로 선택하세요.")
        return
    v = ds.select(ids)
    n = len(v)
    if brand is not None:
        v.set_values("brand", [brand] * n)
    if series is not None:
        v.set_values("series", [series] * n)
    if model is not None:
        v.set_values("model", [model] * n)
    v.tag_samples("relabeled")
    session.refresh()
    print(f"{n}장 라벨 적용 → brand={brand}, series={series}, model={model}")


def keep():
    v = _sel_view()
    v.tag_samples("keep")
    v.untag_samples("reject")
    session.refresh()
    print(f"{len(v)}장 keep")


def reject():
    v = _sel_view()
    v.tag_samples("reject")
    v.untag_samples("keep")
    session.refresh()
    print(f"{len(v)}장 reject")


def summary():
    print("stage:", ds.count_values("stage"))
    print("sample tags:", ds.count_sample_tags())


def promote_keeps():
    """keep 표시된 review 샘플을 training 으로 승급.

    FiftyOne 의 현재 brand/series/model(사람이 고친 값)을 manifest 에 기록하고,
    review 원본 파일을 새 라벨 경로의 training/ 으로 복사 + labels.tsv export.
    """
    review_recs = storage.latest_by_hash(stage="review")  # content_hash -> manifest 레코드
    kept = ds.match_tags("keep").match(F("stage") == "review")
    promoted = []
    for s in kept:
        h = s["content_hash"]
        base = review_recs.get(h)
        if not base:
            continue
        src = storage.DATA_ROOT / base["path"]
        if not src.exists():
            continue
        ext = src.suffix.lstrip(".") or "png"
        dst = storage.stage_image_path("training", s["brand"], s["series"], s["model"],
                                       s["modality"], h, ext)
        if not dst.exists():
            shutil.copy2(src, dst)
        promoted.append({
            **base,
            "brand": s["brand"], "series": s["series"], "model": s["model"],
            "stage": "training", "status": "approved",
            "path": storage.rel(dst),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        })
        s["stage"] = "training"
        s["filepath"] = str(dst.resolve())
        s.save()
    storage.append_manifest(promoted)
    storage.export_labels_tsv()
    session.refresh()
    print(f"training 승급 {len(promoted)}장 + labels.tsv export")


print("""
─────────────────────────────────────────────
 라벨링 세션 준비됨.  App → http://localhost:5151
 1) App 에서 stage=review + modality=catalog 필터
 2) 라벨링할 샘플 체크박스 선택
 3) 프롬프트:  label(series='SSII', model='...')  →  keep()
 4) 다 되면:   promote_keeps()
 헬퍼: sel() / label() / keep() / reject() / summary() / promote_keeps()
─────────────────────────────────────────────
""")
