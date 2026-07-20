"""App에서 series 필드를 직접 편집한 review 샘플을 training 으로 승급. 비대화식(REPL X).

권장 워크플로:
  1) bash scripts/review.sh                # FiftyOne App http://localhost:5151
  2) App에서 샘플의 series 필드를 직접 수정 (예: SSII, SSIII)   # FiftyOne 직접 편집
  3) bash scripts/promote_reviewed.sh      # series 지정된(≠_unknown) review → training

규칙:
  - stage=review 이고 series 가 _unknown/빈값이 아니며 'reject' 태그 없는 샘플을 승급.
  - 데이터셋 재빌드 X (App 편집 보존). load_dataset 만 사용.
  - model 직접 편집했으면 그 값, 아니면 _unknown.
"""
import shutil
from collections import Counter
from datetime import datetime, timezone

import fiftyone as fo
from fiftyone import ViewField as F

from drheri_pipeline import storage

DATASET = "drheri"
UNSET = ["_unknown", ""]


def main():
    if DATASET not in fo.list_datasets():
        print("데이터셋 없음. 먼저 bash scripts/review.sh 로 App 을 띄우세요.")
        return
    ds = fo.load_dataset(DATASET)
    review_recs = storage.latest_by_hash(stage="review")

    # series 가 지정된 review 샘플 (직접 편집분)
    v = (ds.match(F("stage") == "review")
           .match(F("series") != None)        # noqa: E711
           .match(~F("series").is_in(UNSET)))

    promoted = []
    skipped_reject = 0
    for s in v:
        if "reject" in (s.tags or []):
            skipped_reject += 1
            continue
        series = s["series"]
        base = review_recs.get(s["content_hash"])
        if not base:
            continue
        src = storage.DATA_ROOT / base["path"]
        if not src.exists():
            continue
        ext = src.suffix.lstrip(".") or "png"
        model = (s["model"] if s.has_field("model") and s["model"] else None) or base.get("model") or "_unknown"
        dst = storage.stage_image_path("training", base["brand"], series, model,
                                       base["modality"], s["content_hash"], ext)
        if not dst.exists():
            shutil.copy2(src, dst)
        promoted.append({
            **base, "series": series, "model": model,
            "stage": "training", "status": "approved",
            "path": storage.rel(dst),
            "approved_at": datetime.now(timezone.utc).isoformat(),
        })
        s["stage"] = "training"
        s["filepath"] = str(dst.resolve())
        s.save()

    storage.append_manifest(promoted)
    storage.export_labels_tsv()
    print(f"승급 {len(promoted)}장 → training/ + labels.tsv  (reject 제외 {skipped_reject})")
    print("승급 series:", dict(Counter(p["series"] for p in promoted)))


if __name__ == "__main__":
    main()
