"""PDF 1건 라벨링 오케스트레이션 — 렌더·필터·병렬·크롭·manifest·FiftyOne."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO

from .. import storage
from ..taxonomy import normalize_brand
from .render import render_pdf
from .detect import detect_fixtures
from .mark import mark_page
from .mapper import map_specs
from .crop_judge import judge_fixtures
from .spec_mark import spec_for_boxes
from .heading_model import model_from_heading
from .geom import diameter_for_boxes
from .partnum_geom import codes_for_boxes, lengths_for_boxes
from .fiftyone_writer import register_prelabeled

# needs_review(사람 검수 필요) 판정용 VLM 신뢰도 바 — 검출 임계값(conf_min)과 분리한 고정값.
# conf_min 은 이제 GDINO 검출 민감도(낮을수록 더 검출)이고, 이건 라벨 신뢰도가 낮은 크롭을 거른다.
NEEDS_REVIEW_CONF = 0.5

# 라벨링 방식 스위치 — 되돌리기용(한 줄로 복귀).
#   "mark": 박스별 단일마크 1콜(기본). is_fixture+모델+지름+길이+코드 통합. set-of-mark 의
#           grounding 붕괴를 마크 1개로 해결(실측 NH p3: 지름 정확·길이 대부분·코드까지).
#   "crop": 박스별 크롭 1콜(is_fixture만) + 스펙은 좌표추출. 빠르지만 좌표는 레이아웃 특화.
#   "som" : 예전 set-of-mark 1콜(mapper.map_specs). 조밀 페이지에서 실패.
JUDGE_MODE = "mark"

# 모델/시리즈를 페이지 제목에서 뽑을지 여부. 기본 False — 실측(Hiossen)에서 '가장 큰 폰트'가
# 시리즈명이 아니라 마케팅 헤드라인("Meet…", "Smiles that last a lifetime")이라 오염이 심함.
# 신뢰 가능한 시리즈 출처(문서 등록 시 default_series 등) 확보 전까지 model 은 비운다(빈칸 > 틀린값).
MODEL_FROM_HEADING = False


@dataclass
class RunSummary:
    pdf: str
    brand: str
    pages: int
    fixture_pages: int
    crops: int
    needs_review: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_page(page, brand, pdf_url, conf_min, log) -> list[dict]:
    """한 페이지 → 크롭 레코드 리스트 (검출 0개면 빈 리스트).

    단일 해상도: 검출·마크·VLM·크롭 모두 page.image 를 쓴다(좌표 환산 없음).
    페이지 단위 예외는 격리해 한 페이지 실패가 전체를 멈추지 않게 한다(스펙 §8).
    """
    try:
        boxes = detect_fixtures(page.image, threshold=conf_min)   # conf_min = GDINO 검출 임계값
        if not boxes:
            return []
        # 박스를 읽기순서(위→아래, 좌→우)로 정렬 후 번호 매김 — 표 읽는 순서와 맞아 VLM 정렬이 쉬워진다
        boxes = sorted(boxes, key=lambda b: (b.xyxy[1], b.xyxy[0]))
        n = len(boxes)
        # 스펙(모델/지름/길이/코드) + is_fixture 를 JUDGE_MODE 로 산출 — 전부 박스순 배열로 통일.
        if JUDGE_MODE == "mark":
            # 단일마크: 박스 1개만 마크한 풀페이지 1콜 → is_fixture+스펙 통합(실측: 지름 정확·길이 대부분).
            specs = spec_for_boxes(page.image, boxes, brand)
            is_fix = [s.is_fixture for s in specs]
            confs = [s.confidence for s in specs]
            evids = [s.evidence for s in specs]
            models = [s.model for s in specs]
            dia_list = [s.diameter for s in specs]
            dia_src_list = ["vlm_mark" if s.diameter else None for s in specs]
            len_list = [s.length for s in specs]
            part_list = [s.part_number for s in specs]
            part_src_list = ["vlm_mark" if s.part_number else None for s in specs]
        else:
            # crop/som: 스펙은 좌표추출 공용, is_fixture 판단 방식만 다름.
            geom_dias = diameter_for_boxes(page.words, boxes)
            code_lists = codes_for_boxes(page.words, boxes)
            len_lists = lengths_for_boxes(page.words, boxes)
            dia_list = [geom_dias[i] if i < len(geom_dias) else None for i in range(n)]
            dia_src_list = ["geom" if d else None for d in dia_list]
            len_list = [len_lists[i] if i < len(len_lists) else None for i in range(n)]
            part_list = [",".join(code_lists[i]) if i < len(code_lists) and code_lists[i] else None
                         for i in range(n)]
            part_src_list = ["text" if p else None for p in part_list]
            if JUDGE_MODE == "som":
                specs = map_specs(mark_page(page.image, boxes), page.image, boxes, brand, page.text)
                is_fix = [s.is_fixture for s in specs]
                confs = [s.confidence for s in specs]
                evids = [s.evidence for s in specs]
                models = [s.model for s in specs]
            else:   # crop
                judges = judge_fixtures(page.image, boxes)
                is_fix = [j.is_fixture for j in judges]
                confs = [j.confidence for j in judges]
                evids = [j.evidence for j in judges]
                # 시리즈=페이지 제목 추출은 마케팅 헤드라인 오염이 심해 기본 비활성(빈칸 > 틀린값).
                page_model = model_from_heading(page.heading, brand) if MODEL_FROM_HEADING else None
                models = [page_model] * n
        recs: list[dict] = []
        seen: set[str] = set()
        for i, b in enumerate(boxes):
            crop = page.image.crop(b.xyxy)
            buf = BytesIO(); crop.save(buf, "PNG"); png = buf.getvalue()
            chash = storage.content_hash(png)
            if chash in seen:
                continue
            seen.add(chash)
            # 모드별로 채운 박스순 스펙 배열을 인덱싱(mark=VLM 단일마크, crop/som=좌표).
            model = models[i]
            diameter = dia_list[i]
            diameter_src = dia_src_list[i]
            part_number = part_list[i]
            part_number_src = part_src_list[i]
            length = len_list[i]
            conf = confs[i]
            is_fixture = is_fix[i]
            # needs_review = 저신뢰·모델없음·비픽스처. 지름/길이 빈칸은 '의도된 것'이라 조건에서 뺀다.
            needs = conf < NEEDS_REVIEW_CONF or not model or is_fixture is False
            dst = storage.stage_image_path("review", brand, "_unknown", "_unknown",
                                           "catalog", chash, "png")
            if not dst.exists():
                dst.write_bytes(png)
            recs.append({
                "content_hash": chash, "path": storage.rel(dst),
                "stage": "review", "status": "review",
                "brand": brand, "model": model, "diameter": diameter, "length": length,
                "part_number": part_number, "part_number_src": part_number_src,
                "ai_confidence": round(conf, 3), "evidence": evids[i] if i < len(evids) else "",
                "is_fixture": is_fixture, "diameter_src": diameter_src,
                "modality": "catalog", "source_id": "catalog_vlm", "source_type": "catalog_vlm",
                "source_page": page.page_no, "page_no": page.page_no,
                "bbox": list(b.xyxy), "needs_review": needs,
                "brand_norm": normalize_brand(brand), "fetched_at": _now(),
                "source_pdf": pdf_url,
                "origin_url": f"{pdf_url}#page={page.page_no}",
            })
        return recs
    except Exception as e:  # noqa: BLE001 — 페이지 단위 예외 격리(§8)
        log(f"[runner] page {page.page_no} 실패 — 건너뜀 ({e})")
        return []


def label_catalog(pdf_url: str, brand: str, pages: str = "", *, dpi: int = 200,
                  conf_min: float = 0.6, max_workers: int = 4, log=print) -> RunSummary:
    def _render_prog(r, t):
        storage.write_progress(r, t, 0, phase="render")   # 렌더 구간 진행("렌더링 X/N")
    pages_list = list(render_pdf(pdf_url, pages, dpi=dpi, log=log, on_progress=_render_prog))
    total = len(pages_list)
    all_recs: list[dict] = []
    fixture_pages = 0
    done = 0
    storage.write_progress(0, total, 0)                 # 렌더 끝 — 검출 구간 시작(phase=process)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for recs in ex.map(lambda p: _process_page(p, brand, pdf_url, conf_min, log), pages_list):
            done += 1
            if recs:
                fixture_pages += 1
                all_recs.extend(recs)
            storage.write_progress(done, total, len(all_recs))   # 페이지 처리마다 갱신
    storage.append_manifest(all_recs)
    register_prelabeled(all_recs, log=log)
    summ = RunSummary(pdf=pdf_url, brand=brand, pages=len(pages_list),
                      fixture_pages=fixture_pages, crops=len(all_recs),
                      needs_review=sum(1 for r in all_recs if r["needs_review"]))
    log(f"[runner] {brand} pages={summ.pages} fixture_pages={summ.fixture_pages} "
        f"crops={summ.crops} needs_review={summ.needs_review}")
    return summ
