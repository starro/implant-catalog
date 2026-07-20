"""needs-label 에서 'accept' 태그된 figure 의 series = suggested_series 로 일괄 채택. 비대화식.

워크플로:
  1) bash scripts/review.sh                # App, view 'needs-label'
  2) App에서 suggested_series 가 맞는 figure 선택 → 태그 'accept'
  3) bash scripts/accept_suggested.sh      # 선택분 series = suggested_series 로 확정
  4) bash scripts/promote_reviewed.sh      # series 채워진 것 → training

제안이 틀린 건 'accept' 안 하고 series 필드를 직접 수정하면 됨.
"""
from fiftyone import ViewField as F
import fiftyone as fo

from drheri_pipeline import storage

DATASET = "drheri"


def main():
    if DATASET not in fo.list_datasets():
        print("데이터셋 없음. review.sh 먼저.")
        return
    ds = fo.load_dataset(DATASET)
    v = ds.match_tags("accept").match(F("stage") == "review")
    recs = {r["content_hash"]: r for r in storage.read_manifest() if r.get("stage") == "review"}
    updated, skipped = [], 0
    for s in v:
        sug = s["suggested_series"] if s.has_field("suggested_series") else None
        if not sug:
            skipped += 1
            continue
        s["series"] = sug
        s.untag_samples("accept")
        s.save()
        base = recs.get(s["content_hash"])
        if base:
            updated.append({**base, "series": sug, "series_resolution": "accepted_suggestion"})
    storage.append_manifest(updated)
    print(f"채택: {len(updated)}장 (series=suggested_series), 제안없어 건너뜀 {skipped}")


if __name__ == "__main__":
    main()
