"""FiftyOne 검수 앱 — manifest.jsonl(출처)에서 데이터셋을 빌드 후 App 실행.

설계 원칙: manifest = source of truth, FiftyOne = view.
Dagster ingest 중의 FiftyOne 쓰기는 별도 단명 프로세스라 영속 DB 동기화가 불안정
(count/len desync) → 여기서 manifest 기준으로 한 프로세스에서 재구성한다.

stage 는 manifest 의 content_hash 별 '최신' 레코드로 결정 (promote 되면 training, 아니면 review).

실행: scripts/review.sh  (DATA_ROOT/PYTHONPATH 설정 후 이 파일 실행)
"""
import fiftyone as fo
from fiftyone import ViewField as F

from drheri_pipeline import storage

DATASET = "drheri"
_STR_FIELDS = ["content_hash", "brand", "series", "surface", "model", "modality",
               "stage", "status", "source_id", "origin_url", "nearby_text",
               "suggested_series", "page_series", "series_resolution"]   # surface=표면처리(SA/CA..), 사람이 라벨


def build_dataset() -> "fo.Dataset":
    """manifest.jsonl 의 content_hash 별 최신 레코드로 FiftyOne 데이터셋 재구성."""
    records = list(storage.latest_by_hash().values())
    if DATASET in fo.list_datasets():
        fo.delete_dataset(DATASET)
    ds = fo.Dataset(DATASET, persistent=True)
    for f in _STR_FIELDS:
        ds.add_sample_field(f, fo.StringField)
    ds.add_sample_field("page_no", fo.IntField)   # 원본 PDF 페이지 — 카탈로그 대조용

    samples = []
    for r in records:
        fp = (storage.DATA_ROOT / r["path"]).resolve()
        if not fp.exists():
            continue
        s = fo.Sample(filepath=str(fp))
        for k in _STR_FIELDS:
            s[k] = (r.get(k) or "")[:500] if k == "nearby_text" else r.get(k)
        s["page_no"] = r.get("page_no")
        samples.append(s)
    ds.add_samples(samples)
    return ds


def build_views(ds) -> None:
    """saved view 자동 생성 — brand/series/modality × stage.

    Saved view 는 서버에 영속 저장되고 App 주소(URL)에 반영되어,
    스크롤·새로고침·재연결에도 안 풀린다(사이드바 임시 필터와 달리).
    드롭다운에서 'GS-review', 'catalog-review' 등을 골라 라벨링.
    """
    def upsert(name, view):
        if name in ds.list_saved_views():
            ds.delete_saved_view(name)
        ds.save_view(name, view)

    for st in ("review", "training"):
        st_view = ds.match(F("stage") == st)
        for b in ds.distinct("brand"):
            if b:
                upsert(f"{b}-{st}", st_view.match(F("brand") == b))
        for s in ds.distinct("series"):
            if s and s != "_unknown":
                upsert(f"{s}-{st}", st_view.match(F("series") == s))
        for m in ds.distinct("modality"):
            if m:
                upsert(f"{m}-{st}", st_view.match(F("modality") == m))

    # 사람이 시리즈/모델을 직접 붙여야 하는 버킷 (자동분류 안 된 review)
    review_v = ds.match(F("stage") == "review")
    unset = (F("series") == None) | F("series").is_in(["_unknown", ""])  # noqa: E711
    upsert("needs-label", review_v.match(unset))
    # 자동분류된 review (페이지텍스트 등) — 검증/일괄승급용
    upsert("auto-classified", review_v.match(~unset))


if __name__ == "__main__":
    import sys
    ds = build_dataset()
    build_views(ds)
    print("count:", ds.count())
    print("stage:", ds.count_values("stage"))
    print("saved views:", ds.list_saved_views())

    # 인자로 saved view 명을 주면 그 view 에 고정(pin)해서 띄움.
    # 주기적 세션 resync 가 사이드바 필터/saved view 선택을 초기화해도,
    # launch_app 에 view 를 직접 넘기면 '표시 베이스' 자체가 그 view 라 풀 수 없다.
    view_name = sys.argv[1] if len(sys.argv) > 1 else None
    target = ds
    if view_name:
        if view_name in ds.list_saved_views():
            target = ds.load_saved_view(view_name)
            print(f"pinned view: {view_name} ({target.count()}장)")
        else:
            print(f"⚠️ saved view '{view_name}' 없음 — 전체로 띄움")

    session = fo.launch_app(target, port=5151)
    session.wait(-1)
