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
from .partnum import parse_length
from .geom import diameter_for_boxes
from .fiftyone_writer import register_prelabeled


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
        boxes = detect_fixtures(page.image)
        if not boxes:
            return []
        # 박스를 읽기순서(위→아래, 좌→우)로 정렬 후 번호 매김 — 표 읽는 순서와 맞아 VLM 정렬이 쉬워진다
        boxes = sorted(boxes, key=lambda b: (b.xyxy[1], b.xyxy[0]))
        marked = mark_page(page.image, boxes)
        specs = map_specs(marked, page.image, boxes, brand, page.text)
        geom_dias = diameter_for_boxes(page.words, boxes)   # 좌표 기반 직경(없으면 None)
        recs: list[dict] = []
        seen: set[str] = set()
        for i, b in enumerate(boxes):
            crop = page.image.crop(b.xyxy)
            buf = BytesIO(); crop.save(buf, "PNG"); png = buf.getvalue()
            chash = storage.content_hash(png)
            if chash in seen:
                continue
            seen.add(chash)
            sp = specs[i] if i < len(specs) else None
            model = sp.model if sp else None
            geom_d = geom_dias[i] if i < len(geom_dias) else None
            # 직경: 기하(좌표) 우선 — 8B 가 못하는 렌더↔직경 위치매칭을 결정적으로. 없으면 VLM.
            diameter = geom_d or (sp.diameter if sp else None)
            diameter_src = "geom" if geom_d else ("vlm" if (sp and sp.diameter) else None)
            # 기하로 직경 잡히면 렌더=직경family 라 length 는 비운다(사람이 필요시 채움). 아니면 VLM/파싱.
            length = (None if geom_d else
                      (sp.length if sp and sp.length else
                       parse_length(brand, sp.part_number if sp else None)))
            conf = sp.confidence if sp else 0.0
            is_fixture = sp.is_fixture if sp else None
            # 검출은 안 버린다(사람이 FiftyOne 에서 발라냄). needs_review = 저신뢰·필드누락·비픽스처.
            needs = conf < conf_min or not model or not diameter or is_fixture is False
            dst = storage.stage_image_path("review", brand, "_unknown", "_unknown",
                                           "catalog", chash, "png")
            if not dst.exists():
                dst.write_bytes(png)
            recs.append({
                "content_hash": chash, "path": storage.rel(dst),
                "stage": "review", "status": "review",
                "brand": brand, "model": model, "diameter": diameter, "length": length,
                "part_number": sp.part_number if sp else None,
                "ai_confidence": round(conf, 3), "evidence": sp.evidence if sp else "",
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
