"""소스 카탈로그 PDF 페이지를 렌더해 FiftyOne 'catalog_pages' 데이터셋 생성 (자동분류 검증용).

manifest 의 카탈로그 figure 가 나온 (pdf, page) 를 모아 그 페이지를 이미지로 렌더하고,
페이지 텍스트로 감지한 시리즈(detected_series)·판정유형(single/multi/none)·figure수를 라벨로 단다.
App dataset 드롭다운에서 'catalog_pages' 선택 → 실제 카탈로그 페이지를 보며 시리즈 판정이 맞는지 확인.

build-only (App 안 띄움). drheri App 떠 있는 상태에서 실행 후 브라우저 새로고침 → 드롭다운 전환.
실행: bash scripts/render_pages.py
"""
import os
from collections import Counter
from pathlib import Path

import fitz
import fiftyone as fo

from drheri_pipeline import storage
from drheri_pipeline.sources.catalog_pdf import _SERIES_RE, _page_series

DATASET = "catalog_pages"
PAGES_DIR = storage.DATA_ROOT / "pages"
DPI = 120


def _resolve_pdf(pdf_ref: str) -> str | None:
    pdf_ref = pdf_ref.replace("file://", "")
    if os.path.exists(pdf_ref):
        return pdf_ref
    hits = list((storage.DATA_ROOT / "raw").rglob(Path(pdf_ref).name))
    return str(hits[0]) if hits else None


def main():
    # (pdf, page) -> figure 수 + figure 들의 series 분포
    pages: dict = {}
    for r in storage.read_manifest():
        if r.get("modality") != "catalog" or r.get("stage") != "review":
            continue
        ou = r.get("origin_url", "")
        if "#page=" not in ou:
            continue
        pdf, pg = ou.rsplit("#page=", 1)
        try:
            pg = int(pg)
        except ValueError:
            continue
        d = pages.setdefault((pdf, pg), {"count": 0, "series": Counter()})
        d["count"] += 1
        d["series"][r.get("series")] += 1

    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    if DATASET in fo.list_datasets():
        fo.delete_dataset(DATASET)
    ds = fo.Dataset(DATASET, persistent=True)
    for f in ["detected_series", "series_resolution", "source_pdf", "figure_series"]:
        ds.add_sample_field(f, fo.StringField)
    ds.add_sample_field("page_no", fo.IntField)
    ds.add_sample_field("figure_count", fo.IntField)

    by_pdf: dict = {}
    for (pdf, pg) in pages:
        by_pdf.setdefault(pdf, set()).add(pg)

    samples = []
    for pdf, pgs in by_pdf.items():
        local = _resolve_pdf(pdf)
        if not local:
            print(f"  PDF 못 찾음: {pdf}")
            continue
        doc = fitz.open(local)
        for pg in sorted(pgs):
            page = doc[pg - 1]
            pix = page.get_pixmap(dpi=DPI)
            out = PAGES_DIR / f"{Path(local).stem}_p{pg:03d}.png"
            pix.save(str(out))
            txt = page.get_text()
            single = _page_series(txt)
            cand = sorted(set(_SERIES_RE.findall(txt)))
            res = "single" if single else ("multi" if cand else "none")
            info = pages[(pdf, pg)]
            s = fo.Sample(filepath=str(out))
            s["page_no"] = pg
            s["figure_count"] = info["count"]
            s["detected_series"] = single or (",".join(cand) if cand else None)
            s["series_resolution"] = res
            s["source_pdf"] = Path(local).name
            s["figure_series"] = ",".join(f"{k}:{v}" for k, v in info["series"].items())
            samples.append(s)
    ds.add_samples(samples)
    # 판정유형별 saved view
    from fiftyone import ViewField as F
    for r in ("single", "multi", "none"):
        name = f"pages-{r}"
        if name in ds.list_saved_views():
            ds.delete_saved_view(name)
        ds.save_view(name, ds.match(F("series_resolution") == r))
    print(f"catalog_pages: {ds.count()} 페이지")
    print("판정 분포:", ds.count_values("series_resolution"))


if __name__ == "__main__":
    main()
