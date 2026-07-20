"""App에서 단 series 태그(SS2/SS3 ...)를 읽어 → series 부여 + training 승급. 비대화식.

REPL 불필요. 워크플로:
  1) bash scripts/review.sh            # FiftyOne App http://localhost:5151
  2) App 에서 이미지 선택 → 태그 추가 (series명: SS2, SS3 ...)   # 순수 GUI 클릭
  3) bash scripts/apply_series.sh      # 태그 읽어 series 부여 + training 승급

규칙:
  - reserved 태그(keep/reject/relabeled)는 series 로 취급하지 않음.
  - 'reject' 태그된 샘플은 제외.
  - 이 스크립트는 데이터셋을 재빌드하지 않음(App 의 태그 보존). load_dataset 만.
  - 한 샘플에 series 태그가 여러 개면 첫 번째만 적용(경고).
"""
import shutil
from datetime import datetime, timezone

import fiftyone as fo
from fiftyone import ViewField as F

from drheri_pipeline import storage

DATASET = "drheri"
RESERVED = {"keep", "reject", "relabeled"}


def main():
    if DATASET not in fo.list_datasets():
        print(f"데이터셋 '{DATASET}' 없음. 먼저 bash scripts/review.sh 로 App 을 띄우세요.")
        return
    ds = fo.load_dataset(DATASET)
    series_tags = [t for t in ds.count_sample_tags() if t not in RESERVED]
    if not series_tags:
        print("series 태그 없음. App 에서 SS2/SS3 같은 태그를 먼저 다세요.")
        return
    print("발견한 series 태그:", series_tags)

    review_recs = storage.latest_by_hash(stage="review")
    promoted = []
    for series in series_tags:
        cnt = 0
        for s in ds.match_tags(series).match(F("stage") == "review"):
            tags = s.tags or []
            if "reject" in tags:
                continue
            multi = [t for t in tags if t not in RESERVED]
            if len(multi) > 1:
                print(f"  ⚠️ {s['content_hash'][:8]} series 태그 다중 {multi} → '{series}' 사용")
            base = review_recs.get(s["content_hash"])
            if not base:
                continue
            src = storage.DATA_ROOT / base["path"]
            if not src.exists():
                continue
            ext = src.suffix.lstrip(".") or "png"
            model = base.get("model") or "_unknown"
            dst = storage.stage_image_path("training", base["brand"], series, model,
                                           base["modality"], s["content_hash"], ext)
            if not dst.exists():
                shutil.copy2(src, dst)
            promoted.append({
                **base, "series": series,
                "stage": "training", "status": "approved",
                "path": storage.rel(dst),
                "approved_at": datetime.now(timezone.utc).isoformat(),
            })
            s["series"] = series
            s["stage"] = "training"
            s["filepath"] = str(dst.resolve())
            s.save()
            cnt += 1
        print(f"series='{series}': {cnt}장 승급")

    storage.append_manifest(promoted)
    storage.export_labels_tsv()
    print(f"총 {len(promoted)}장 → training/ + labels.tsv")


if __name__ == "__main__":
    main()
