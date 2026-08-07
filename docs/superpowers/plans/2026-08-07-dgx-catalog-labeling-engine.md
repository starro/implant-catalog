# DGX 카탈로그 자동 라벨링 엔진 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카탈로그 PDF 한 건에서 임플란트 픽스처를 검출·크롭하고 각 크롭에 brand/model/diameter(+length)를 미리 채운 라벨로 FiftyOne("drheri") 샘플을 생성해, 사람이 확인·수정·keep/reject 만 하면 되게 한다.

**Architecture:** GPU 작업(Grounding DINO 검출, Qwen3-VL 매핑)은 DGX 의 **웜 HTTP 서비스** 두 개(vLLM :8000, GDINO :8100)로 두고, 오케스트레이션 엔진은 torch 없는 가벼운 httpx/pillow/pymupdf/fiftyone 클라이언트로 둘을 호출한다. 페이지를 **고해상도 마스터 + 다운스케일 뷰**로 이원 렌더 — 검출·VLM 은 뷰(속도), 크롭은 마스터(품질). 기존 `storage`/`taxonomy`/`review`("drheri" 데이터셋) 자산을 재사용한다.

**Tech Stack:** Python 3.11, httpx, Pillow, PyMuPDF(fitz), FiftyOne, (GPU 컨테이너 측) transformers 4.57 Grounding DINO + vLLM Qwen3-VL-8B-Instruct.

## Global Constraints

- Python `>=3.11,<3.12` (pyproject 고정). 신규 엔진 코드는 표준 라이브러리 + 기존 코어 deps(httpx, pillow, pymupdf, fiftyone)만 쓴다. torch/transformers 는 **엔진에 넣지 않는다**(GPU 컨테이너 전용).
- 무거운/선택 의존성은 **함수 안에서 지연 import**(기존 `catalog_pdf`/`review` 패턴). 모듈 import 만으로 fiftyone/fitz 를 끌어오지 않는다.
- 시간은 UTC ISO8601 문자열(`datetime.now(timezone.utc).isoformat()`), 기존 `_now()` 패턴 따른다.
- **멱등성**: 크롭은 `storage.content_hash(png)` 로 중복 제거. 재수집해도 manifest·FiftyOne 이 안 부푼다.
- **해상도 이원화**: 검출·VLM 입력은 다운스케일 뷰, 크롭은 고해상도 마스터. 뷰→마스터는 단일 `scale` 계수로 환산.
- FiftyOne 데이터셋 이름은 기존과 동일한 `"drheri"`(review.py `DATASET`). 신규 라벨 필드를 그 데이터셋에 증분 추가한다.
- 새 코드 위치: `drheri_pipeline/labeling/` 서브패키지. 테스트는 기존 관례대로 `tests/` 평면 배치.
- GPU 서비스 호출 규약(스펙 §9, 검증됨): vLLM `POST http://127.0.0.1:8000/v1/chat/completions` model `qwen3vl`; GDINO transformers `post_process_grounded_object_detection(threshold=…, text_threshold=…)`(주의: `box_threshold` 아님), 라벨은 `text_labels`, 프롬프트 `"a gray implant object"`, threshold≈0.3.

---

## File Structure

```
drheri_pipeline/
  sources/pdf_util.py         # (신규) parse_pages / fetch_pdf_bytes — catalog_pdf 에서 lift (DRY)
  labeling/
    __init__.py
    render.py                 # 이원 렌더: 고해상도 마스터 + 다운스케일 뷰 (+ scale)
    detect.py                 # GDINO HTTP 서비스 클라이언트 + 좌표 스케일 헬퍼
    mark.py                   # set-of-mark: 뷰에 번호 박스 오버레이
    mapper.py                 # Qwen3-VL vLLM 클라이언트 (프롬프트·파싱·하이브리드 재시도)
    partnum.py                # part_number → length 파서 (범용 + 확장 훅)
    fiftyone_writer.py        # 미리라벨 크롭을 "drheri" 데이터셋에 증분 등록
    runner.py                 # PDF 1건 오케스트레이션 (필터·병렬·크롭·manifest)
    cli.py                    # label_catalog 엔트리포인트
scripts/
  gdino_server.py             # (신규) GPU 컨테이너용 작은 GDINO HTTP 서비스
docs/
  DGX_LABELING_DEPLOY.md      # (신규) DGX 배치 절차 (NAS 마운트·서비스·스모크)
tests/
  test_pdf_util.py test_render.py test_partnum.py test_detect.py
  test_mark.py test_mapper.py test_fiftyone_writer.py test_runner.py test_cli.py
```

기존 재사용(수정 없음): `storage.py`, `taxonomy.py`, `normalize.py`, `review.py`.

---

## Task 1: pdf_util — parse_pages / fetch_pdf_bytes 를 공용 모듈로 lift

기존 `catalog_pdf._parse_pages`/`_fetch_pdf_bytes` 는 새 렌더러도 필요하다. private 재활용/중복 대신 공용 모듈로 올리고, 기존 모듈은 재-export 로 호환 유지(기존 테스트 무손상).

**Files:**
- Create: `drheri_pipeline/sources/pdf_util.py`
- Modify: `drheri_pipeline/sources/catalog_pdf.py:53-111` (두 함수 본문 → import 로 대체)
- Test: `tests/test_pdf_util.py`

**Interfaces:**
- Produces:
  - `parse_pages(pages: str) -> list[int] | None` (기존 `_parse_pages` 와 동일 동작)
  - `fetch_pdf_bytes(url: str, log=print) -> tuple[bytes, str]` (기존 `_fetch_pdf_bytes` 와 동일)

- [ ] **Step 1: Write the failing test**

`tests/test_pdf_util.py`:
```python
import pytest
from drheri_pipeline.sources import pdf_util


def test_parse_pages_ranges_and_dedup():
    assert pdf_util.parse_pages("40-42, 12-14, 13") == [12, 13, 14, 40, 41, 42]
    assert pdf_util.parse_pages("") is None
    assert pdf_util.parse_pages("12") == [12]


def test_parse_pages_rejects_bad_input():
    with pytest.raises(ValueError):
        pdf_util.parse_pages("12-")
    with pytest.raises(ValueError):
        pdf_util.parse_pages("0")


def test_fetch_pdf_bytes_local_file(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    data, name = pdf_util.fetch_pdf_bytes(str(f))
    assert data == b"%PDF-1.4 test" and name == "a.pdf"


def test_catalog_pdf_still_exposes_private_aliases():
    # 기존 호출부/테스트 호환: catalog_pdf 가 여전히 같은 동작을 노출한다.
    from drheri_pipeline.sources import catalog_pdf
    assert catalog_pdf._parse_pages("1,2") == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_pdf_util.py -v`
Expected: FAIL — `ModuleNotFoundError: drheri_pipeline.sources.pdf_util`

- [ ] **Step 3: Implement pdf_util.py**

`drheri_pipeline/sources/pdf_util.py` — 기존 `catalog_pdf._parse_pages`/`_fetch_pdf_bytes` 본문을 그대로 옮기고 공개명으로:
```python
"""PDF 입력 공용 유틸 — 페이지 지정 파싱 + URL/파일 바이트 취득.

catalog_pdf(구 DocLayout 경로)와 labeling(신 GDINO+VLM 경로)이 공유한다.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

_UA = {"User-Agent": "Mozilla/5.0"}


def parse_pages(pages: str) -> list[int] | None:
    """'' → None(전체), '12' → [12], '12-16' → [12..16], 정렬·중복제거. 불량 입력은 ValueError."""
    pages = (pages or "").strip()
    if not pages:
        return None
    result: set[int] = set()
    for token in pages.replace(" ", "").split(","):
        if not token:
            continue
        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(f"잘못된 페이지 범위: '{token}' (예: 12-26)")
            lo, hi = int(parts[0]), int(parts[1])
            if lo < 1 or hi < 1:
                raise ValueError(f"페이지는 1 이상이어야 합니다: '{token}'")
            if lo > hi:
                raise ValueError(f"범위 시작이 끝보다 큽니다: '{token}' (예: 12-26)")
            result.update(range(lo, hi + 1))
        else:
            n = int(token)
            if n < 1:
                raise ValueError(f"페이지는 1 이상이어야 합니다: '{token}'")
            result.add(n)
    return sorted(result)


def fetch_pdf_bytes(url: str, log=print) -> tuple[bytes, str]:
    """http(s) URL · file:// · 로컬 경로 모두 지원 → (bytes, 파일명)."""
    local = Path(url)
    if local.exists():
        log(f"[pdf_util] local file {url}")
        return local.read_bytes(), local.name
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        log(f"[pdf_util] download {url}")
        resp = httpx.get(url, headers=_UA, timeout=120, follow_redirects=True)
        resp.raise_for_status()
        return resp.content, (Path(parsed.path).name or "catalog.pdf")
    if parsed.scheme == "file":
        from urllib.request import url2pathname
        fp = Path(url2pathname(parsed.path))
        return fp.read_bytes(), fp.name
    raise ValueError(f"지원하지 않는 PDF 경로: {url}")
```

- [ ] **Step 4: Re-point catalog_pdf to the shared functions**

`catalog_pdf.py`: `_parse_pages`/`_fetch_pdf_bytes` 정의를 지우고 상단에 재-export 추가(기존 `ingest` 내부 호출·기존 테스트가 그대로 동작):
```python
from .pdf_util import fetch_pdf_bytes as _fetch_pdf_bytes, parse_pages as _parse_pages
```
(기존 `_UA` 상수도 pdf_util 로 이동했으므로 catalog_pdf 의 `_UA` 정의는 제거.)

- [ ] **Step 5: Run tests to verify pass (신규 + 기존 회귀)**

Run: `cd data-pipeline && python -m pytest tests/test_pdf_util.py tests/test_parse_pages.py -v`
Expected: PASS (both)

- [ ] **Step 6: Commit**

```bash
git add drheri_pipeline/sources/pdf_util.py drheri_pipeline/sources/catalog_pdf.py tests/test_pdf_util.py
git commit -m "refactor: PDF 페이지파싱·바이트취득을 pdf_util 공용모듈로 lift"
```

---

## Task 2: render — 이원 해상도 페이지 렌더러

페이지를 고해상도 마스터(크롭용)와 다운스케일 뷰(검출·VLM용)로 렌더하고, 뷰→마스터 `scale` 계수와 페이지 텍스트를 함께 돌려준다.

**Files:**
- Create: `drheri_pipeline/labeling/__init__.py` (빈 파일), `drheri_pipeline/labeling/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `pdf_util.parse_pages`
- Produces:
  - `@dataclass RenderedPage: page_no:int; master: "PIL.Image.Image"; view: "PIL.Image.Image"; scale: float; text: str`
    (`scale` = master.width / view.width; 뷰 좌표 × scale = 마스터 좌표)
  - `render_pdf(pdf_path, pages: str = "", *, master_dpi: int = 300, view_long_px: int = 1024, log=print) -> Iterator[RenderedPage]`

- [ ] **Step 1: Write the failing test**

`tests/test_render.py`:
```python
import fitz
from drheri_pipeline.labeling import render


def _make_pdf(path, pages=2):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=595, height=842)  # A4 pt
        pg.insert_text((72, 72), f"REF 58160 page {i+1}")
    doc.save(str(path)); doc.close()


def test_render_pdf_dual_resolution(tmp_path):
    pdf = tmp_path / "c.pdf"; _make_pdf(pdf, pages=2)
    out = list(render.render_pdf(str(pdf), master_dpi=300, view_long_px=512))
    assert len(out) == 2
    p = out[0]
    assert p.page_no == 1
    assert max(p.view.size) == 512                 # 뷰 긴 변 고정
    assert p.master.width > p.view.width           # 마스터가 더 큼
    assert abs(p.scale - p.master.width / p.view.width) < 1e-6
    assert "REF 58160" in p.text                   # 페이지 텍스트 추출


def test_render_pdf_page_filter(tmp_path):
    pdf = tmp_path / "c.pdf"; _make_pdf(pdf, pages=3)
    out = list(render.render_pdf(str(pdf), pages="2"))
    assert [p.page_no for p in out] == [2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: drheri_pipeline.labeling`

- [ ] **Step 3: Implement render.py**

```python
"""이원 해상도 페이지 렌더 — 고해상도 마스터(크롭용) + 다운스케일 뷰(검출·VLM용)."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterator

from .pdf_util_import import parse_pages  # noqa  (아래 실제 import 로 대체)
```
실제 상단 import 는:
```python
from ..sources.pdf_util import parse_pages
```
본문:
```python
@dataclass
class RenderedPage:
    page_no: int
    master: "object"   # PIL.Image.Image (지연 import 회피용 느슨한 타입)
    view: "object"
    scale: float
    text: str


def render_pdf(pdf_path, pages: str = "", *, master_dpi: int = 300,
               view_long_px: int = 1024, log=print) -> Iterator[RenderedPage]:
    import fitz
    from PIL import Image

    doc = fitz.open(str(pdf_path))
    want = parse_pages(pages)
    idxs = ([n - 1 for n in want if 1 <= n <= doc.page_count]
            if want else range(doc.page_count))
    for i in idxs:
        page = doc[i]
        pix = page.get_pixmap(dpi=master_dpi)
        master = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
        long_side = max(master.size)
        ratio = view_long_px / long_side
        view = master.resize((max(1, round(master.width * ratio)),
                              max(1, round(master.height * ratio))))
        scale = master.width / view.width
        yield RenderedPage(page_no=i + 1, master=master, view=view,
                           scale=scale, text=page.get_text())
    doc.close()
```
(주: `pdf_util_import` 줄은 착오 — 실제 코드엔 넣지 말고 `from ..sources.pdf_util import parse_pages` 만 둔다.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/labeling/__init__.py drheri_pipeline/labeling/render.py tests/test_render.py
git commit -m "feat(labeling): 이원 해상도 페이지 렌더러(마스터+뷰)"
```

---

## Task 3: partnum — part_number → length 파서

length 는 픽셀 측정 불가 → part number 에서 얻는다. 브랜드별 포맷은 제각각이므로 v1 은 **범용 추출**(문자열에서 길이로 보이는 mm 토큰) + 브랜드별 확장 훅만 둔다.

**Files:**
- Create: `drheri_pipeline/labeling/partnum.py`
- Test: `tests/test_partnum.py`

**Interfaces:**
- Produces: `parse_length(brand: str | None, part_number: str | None) -> str | None`
  (반환은 정규화된 mm 문자열 예: `"11.5"`, 못 찾으면 None)

- [ ] **Step 1: Write the failing test**

`tests/test_partnum.py`:
```python
from drheri_pipeline.labeling import partnum


def test_parse_length_generic_mm_token():
    # 흔한 포맷: 끝의 두 자리쌍이 직경·길이 (예: BEGO 58xxx 는 표에서 length 별도)
    assert partnum.parse_length("BEGO", "S 4.1 x 11.5") == "11.5"
    assert partnum.parse_length("Osstem", "L=10mm") == "10"


def test_parse_length_none_when_absent():
    assert partnum.parse_length("BEGO", None) is None
    assert partnum.parse_length("BEGO", "58160") is None   # 순수 REF 코드엔 길이 없음


def test_parse_length_picks_plausible_range():
    # 6~20mm 범위만 length 후보 (직경 3~7 과 구분)
    assert partnum.parse_length("X", "3.75 / 13") == "13"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_partnum.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'parse_length'`

- [ ] **Step 3: Implement partnum.py**

```python
"""part_number → length(mm) 파서.

브랜드별 포맷이 제각각이라 v1 은 범용 규칙: 문자열에서 임플란트 길이로 그럴듯한
mm 값(6~20)을 뽑는다. 브랜드별 정밀 규칙은 BRAND_RULES 에 추가(확장 훅)."""
from __future__ import annotations

import re

_NUM = re.compile(r"\d+(?:\.\d+)?")

# 브랜드별 정밀 파서 확장 지점 (v1 비어있음). 값은 (part_number)->str|None 함수.
BRAND_RULES: dict[str, "callable"] = {}


def _generic_length(part_number: str) -> str | None:
    """6~20mm 범위의 마지막 그럴듯한 값 = length 후보(직경 3~7 과 구분)."""
    cands = [t for t in _NUM.findall(part_number) if 6.0 <= float(t) <= 20.0]
    if not cands:
        return None
    v = cands[-1]
    return v[:-2] if v.endswith(".0") else v


def parse_length(brand: str | None, part_number: str | None) -> str | None:
    if not part_number:
        return None
    rule = BRAND_RULES.get((brand or "").strip().lower())
    if rule:
        got = rule(part_number)
        if got:
            return got
    return _generic_length(part_number)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_partnum.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/labeling/partnum.py tests/test_partnum.py
git commit -m "feat(labeling): part_number→length 범용 파서 + 브랜드 확장훅"
```

---

## Task 4: GDINO HTTP 서비스 + detect 클라이언트

GPU 컨테이너에 GDINO 를 작은 HTTP 서비스로 띄우고(웜 유지), 엔진은 httpx 클라이언트로 박스를 받는다. 좌표 스케일 환산 헬퍼 포함.

**Files:**
- Create: `scripts/gdino_server.py` (GPU 컨테이너에서 실행), `drheri_pipeline/labeling/detect.py`
- Test: `tests/test_detect.py`

**Interfaces:**
- Consumes: `render.RenderedPage`
- Produces:
  - `@dataclass Box: score: float; xyxy: tuple[int,int,int,int]`
  - `detect_fixtures(view_img, *, url="http://127.0.0.1:8100/detect", prompt="a gray implant object", threshold=0.3) -> list[Box]` (뷰 좌표계 Box)
  - `to_master(box: Box, scale: float) -> Box` (마스터 좌표계로 환산)
- 서비스 계약: `POST /detect` body `{"image_b64": <png b64>, "prompt": str, "threshold": float}` → `{"boxes":[{"score":float,"xyxy":[x1,y1,x2,y2]}]}`

- [ ] **Step 1: Write the failing test** (서비스는 httpx mock, 스케일은 순수함수)

`tests/test_detect.py`:
```python
from PIL import Image
from drheri_pipeline.labeling import detect


def test_to_master_scales_coords():
    b = detect.Box(score=0.5, xyxy=(10, 20, 30, 40))
    m = detect.to_master(b, scale=2.0)
    assert m.xyxy == (20, 40, 60, 80) and m.score == 0.5


def test_detect_fixtures_parses_service_response(monkeypatch):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"boxes": [{"score": 0.52, "xyxy": [1, 2, 3, 4]}]}

    def fake_post(url, json=None, timeout=None):
        assert json["prompt"] == "a gray implant object"
        return Resp()

    monkeypatch.setattr(detect.httpx, "post", fake_post)
    boxes = detect.detect_fixtures(Image.new("RGB", (8, 8)))
    assert len(boxes) == 1 and boxes[0].xyxy == (1, 2, 3, 4) and boxes[0].score == 0.52
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_detect.py -v`
Expected: FAIL — `ModuleNotFoundError: ...labeling.detect`

- [ ] **Step 3: Implement detect.py**

```python
"""Grounding DINO HTTP 서비스 클라이언트 + 좌표 스케일 환산."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO

import httpx


@dataclass
class Box:
    score: float
    xyxy: tuple[int, int, int, int]


def _png_b64(img) -> str:
    buf = BytesIO(); img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def detect_fixtures(view_img, *, url: str = "http://127.0.0.1:8100/detect",
                    prompt: str = "a gray implant object", threshold: float = 0.3) -> list[Box]:
    resp = httpx.post(url, json={"image_b64": _png_b64(view_img),
                                 "prompt": prompt, "threshold": threshold}, timeout=60)
    resp.raise_for_status()
    return [Box(score=float(b["score"]), xyxy=tuple(int(v) for v in b["xyxy"]))
            for b in resp.json()["boxes"]]


def to_master(box: Box, scale: float) -> Box:
    x1, y1, x2, y2 = box.xyxy
    return Box(score=box.score, xyxy=(round(x1 * scale), round(y1 * scale),
                                      round(x2 * scale), round(y2 * scale)))
```

- [ ] **Step 4: Implement gdino_server.py** (GPU 컨테이너 전용, 검증된 규약 사용)

`scripts/gdino_server.py`:
```python
"""GPU 컨테이너용 Grounding DINO HTTP 서비스 (웜 유지). 컨테이너 안에서:
    python scripts/gdino_server.py            # :8100
transformers 4.57 규약: post_process_grounded_object_detection(threshold=, text_threshold=)."""
import base64
from io import BytesIO

import torch
import uvicorn
from fastapi import FastAPI
from PIL import Image
from transformers import AutoProcessor, GroundingDinoForObjectDetection

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_proc = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-base")
_model = GroundingDinoForObjectDetection.from_pretrained(
    "IDEA-Research/grounding-dino-base").to(DEVICE).eval()
app = FastAPI()


@app.post("/detect")
def detect(body: dict):
    img = Image.open(BytesIO(base64.b64decode(body["image_b64"]))).convert("RGB")
    text = body.get("prompt", "a gray implant object")
    thr = float(body.get("threshold", 0.3))
    inp = _proc(images=img, text=text, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        out = _model(**inp)
    res = _proc.post_process_grounded_object_detection(
        out, inp.input_ids, threshold=thr, text_threshold=thr,
        target_sizes=[img.size[::-1]])[0]
    boxes = [{"score": round(float(s), 3),
              "xyxy": [int(v) for v in box.tolist()]}
             for box, s in zip(res["boxes"], res["scores"])]
    return {"boxes": boxes}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_detect.py -v`
Expected: PASS (gdino_server 는 여기서 실행 안 함 — DGX 스모크는 Task 10)

- [ ] **Step 6: Commit**

```bash
git add drheri_pipeline/labeling/detect.py scripts/gdino_server.py tests/test_detect.py
git commit -m "feat(labeling): GDINO HTTP 서비스 + detect 클라이언트·좌표환산"
```

---

## Task 5: mark — set-of-mark 번호 박스 오버레이

뷰 이미지에 검출 박스를 번호와 함께 그려, VLM 이 "몇 번 박스"로 스펙을 답하게 한다.

**Files:**
- Create: `drheri_pipeline/labeling/mark.py`
- Test: `tests/test_mark.py`

**Interfaces:**
- Consumes: `detect.Box` (뷰 좌표계)
- Produces: `mark_page(view_img, boxes: list[Box]) -> "PIL.Image.Image"` (원본 훼손 없이 복사본에 그림; 박스 순서 = 번호 0..N-1)

- [ ] **Step 1: Write the failing test**

`tests/test_mark.py`:
```python
from PIL import Image
from drheri_pipeline.labeling import mark
from drheri_pipeline.labeling.detect import Box


def test_mark_page_returns_copy_same_size():
    img = Image.new("RGB", (100, 100), "white")
    boxes = [Box(0.5, (10, 10, 40, 40)), Box(0.5, (50, 50, 90, 90))]
    out = mark.mark_page(img, boxes)
    assert out.size == img.size
    assert out is not img                      # 원본 불변
    assert list(img.getdata()) == list(Image.new("RGB", (100, 100), "white").getdata())


def test_mark_page_empty_boxes():
    img = Image.new("RGB", (20, 20), "white")
    out = mark.mark_page(img, [])
    assert out.size == (20, 20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_mark.py -v`
Expected: FAIL — `ModuleNotFoundError: ...labeling.mark`

- [ ] **Step 3: Implement mark.py**

```python
"""set-of-mark — 뷰 이미지에 번호 박스를 그린다(VLM 이 번호로 스펙 응답)."""
from __future__ import annotations


def mark_page(view_img, boxes):
    from PIL import ImageDraw
    out = view_img.copy()
    draw = ImageDraw.Draw(out)
    for i, b in enumerate(boxes):
        x1, y1, x2, y2 = b.xyxy
        draw.rectangle((x1, y1, x2, y2), outline=(255, 0, 0), width=3)
        draw.text((x1 + 2, max(0, y1 - 12)), str(i), fill=(255, 0, 0))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_mark.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/labeling/mark.py tests/test_mark.py
git commit -m "feat(labeling): set-of-mark 번호 박스 오버레이"
```

---

## Task 6: mapper — Qwen3-VL vLLM 클라이언트 (하이브리드)

번호 박스 뷰 + 페이지 텍스트를 주고 박스별 스펙을 1콜로 받는다. 응답 항목수가 박스수와 안 맞으면 그 페이지를 박스별 개별 크롭 콜로 재시도한다.

**Files:**
- Create: `drheri_pipeline/labeling/mapper.py`
- Test: `tests/test_mapper.py`

**Interfaces:**
- Consumes: 번호 박스가 그려진 뷰 이미지, `detect.Box` 리스트, 브랜드, 페이지 텍스트
- Produces:
  - `@dataclass BoxSpec: index:int; model:str|None; diameter:str|None; length:str|None; part_number:str|None; confidence:float; evidence:str`
  - `map_specs(marked_view, master, boxes, brand, page_text, *, url=".../v1/chat/completions", model_name="qwen3vl") -> list[BoxSpec]`
    (하이브리드: 1콜 결과 길이 ≠ len(boxes) 이면 박스별 개별 콜 fallback)

- [ ] **Step 1: Write the failing test**

`tests/test_mapper.py`:
```python
import json
from PIL import Image
from drheri_pipeline.labeling import mapper
from drheri_pipeline.labeling.detect import Box


def _resp(payload):
    class R:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return R()


def test_map_specs_single_call_happy(monkeypatch):
    calls = {"n": 0}
    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return _resp([{"index": 0, "model": "SC", "diameter": "4.1", "length": None,
                       "part_number": "58160", "confidence": 0.9, "evidence": "SC 4.1"}])
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    specs = mapper.map_specs(view, master, [Box(0.5, (1, 1, 5, 5))], "BEGO", "REF 58160")
    assert calls["n"] == 1
    assert specs[0].model == "SC" and specs[0].diameter == "4.1" and specs[0].index == 0


def test_map_specs_count_mismatch_falls_back_to_per_box(monkeypatch):
    # 1콜이 2박스인데 1개만 반환 → 박스별 개별콜(2회) fallback
    seq = [
        _resp([{"index": 0, "model": "A", "diameter": "4.1", "confidence": 0.8}]),  # mismatch
        _resp([{"index": 0, "model": "A", "diameter": "4.1", "confidence": 0.8}]),  # per-box 0
        _resp([{"index": 0, "model": "B", "diameter": "5.0", "confidence": 0.7}]),  # per-box 1
    ]
    def fake_post(url, json=None, timeout=None): return seq.pop(0)
    monkeypatch.setattr(mapper.httpx, "post", fake_post)
    view = Image.new("RGB", (20, 20)); master = Image.new("RGB", (40, 40))
    boxes = [Box(0.5, (1, 1, 5, 5)), Box(0.5, (6, 6, 9, 9))]
    specs = mapper.map_specs(view, master, boxes, "BEGO", "txt")
    assert [s.model for s in specs] == ["A", "B"] and len(specs) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_mapper.py -v`
Expected: FAIL — `ModuleNotFoundError: ...labeling.mapper`

- [ ] **Step 3: Implement mapper.py**

```python
"""Qwen3-VL(vLLM) 스펙 매퍼 — set-of-mark 1콜 기본, 항목수 불일치 시 박스별 개별콜."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from io import BytesIO

import httpx

_URL = "http://127.0.0.1:8000/v1/chat/completions"

_SYS = ("You read dental implant catalog pages. Return ONLY JSON. "
        "For each numbered red box, give the fixture's spec from the page text/table.")
_PROMPT = ('Return a JSON array. One object per numbered box: '
           '{{"index":int,"model":str|null,"diameter":str|null,"length":str|null,'
           '"part_number":str|null,"confidence":0..1,"evidence":str}}. '
           'Brand is {brand}. Page text:\n{page_text}')


@dataclass
class BoxSpec:
    index: int
    model: str | None
    diameter: str | None
    length: str | None
    part_number: str | None
    confidence: float
    evidence: str


def _b64(img) -> str:
    buf = BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _spec(d: dict) -> BoxSpec:
    return BoxSpec(index=int(d.get("index", 0)), model=d.get("model"),
                   diameter=d.get("diameter"), length=d.get("length"),
                   part_number=d.get("part_number"),
                   confidence=float(d.get("confidence", 0.0)),
                   evidence=(d.get("evidence") or "")[:300])


def _call(img, text, url, model_name) -> list[dict]:
    body = {"model": model_name, "temperature": 0, "max_tokens": 900,
            "messages": [{"role": "system", "content": _SYS},
                         {"role": "user", "content": [
                             {"type": "text", "text": text},
                             {"type": "image_url", "image_url": {"url": _b64(img)}}]}]}
    resp = httpx.post(url, json=body, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    start, end = content.find("["), content.rfind("]")
    return json.loads(content[start:end + 1]) if start >= 0 else []


def map_specs(marked_view, master, boxes, brand, page_text, *,
              url: str = _URL, model_name: str = "qwen3vl") -> list[BoxSpec]:
    text = _PROMPT.format(brand=brand, page_text=(page_text or "")[:2000])
    try:
        rows = _call(marked_view, text, url, model_name)
    except Exception:
        rows = []
    if len(rows) == len(boxes) and boxes:
        return [_spec({**r, "index": i}) for i, r in enumerate(sorted(rows, key=lambda x: x.get("index", 0)))]
    # 항목수 불일치 → 박스별 개별콜(크롭 뷰) fallback
    out: list[BoxSpec] = []
    for i, b in enumerate(boxes):
        crop = marked_view.crop(b.xyxy)
        one = ('Return a JSON array with ONE object for the implant fixture shown: '
               '{{"index":0,"model":str|null,"diameter":str|null,"length":str|null,'
               '"part_number":str|null,"confidence":0..1,"evidence":str}}. '
               'Brand is {brand}. Page text:\n{page_text}').format(
                   brand=brand, page_text=(page_text or "")[:2000])
        try:
            r = _call(crop, one, url, model_name)
            out.append(_spec({**(r[0] if r else {}), "index": i}))
        except Exception:
            out.append(_spec({"index": i, "confidence": 0.0}))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_mapper.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/labeling/mapper.py tests/test_mapper.py
git commit -m "feat(labeling): Qwen3-VL 스펙매퍼(set-of-mark 1콜 + 박스별 fallback)"
```

---

## Task 7: fiftyone_writer — 미리라벨 크롭을 "drheri" 에 등록

크롭 레코드를 기존 "drheri" 데이터셋에 증분 등록하되, 신규 라벨 필드(model/diameter/length/part_number/ai_confidence/evidence/source_page/box)와 `needs_review` 태그를 채운다. 기존 keep/reject·promote 흐름이 그대로 뒷단을 담당한다.

**Files:**
- Create: `drheri_pipeline/labeling/fiftyone_writer.py`
- Test: `tests/test_fiftyone_writer.py`

**Interfaces:**
- Consumes: manifest 스타일 레코드 dict (Task 8 이 생성; 필드는 아래 Produces 참조)
- Produces:
  - `register_prelabeled(records: list[dict], log=print) -> int`
  - 레코드 필수 키: `content_hash, path(rel), brand, model, diameter, length, part_number,
    ai_confidence(float), evidence, source_page(int), bbox(list[int]), needs_review(bool)`

- [ ] **Step 1: Write the failing test** (fiftyone 지연 import — 미설치 시 스킵)

`tests/test_fiftyone_writer.py`:
```python
import pytest
from drheri_pipeline.labeling import fiftyone_writer

fo = pytest.importorskip("fiftyone")


def test_register_prelabeled_sets_fields_and_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(fiftyone_writer.storage, "DATA_ROOT", tmp_path)
    img = tmp_path / "crop.png"
    from PIL import Image; Image.new("RGB", (10, 10)).save(img)
    ds_name = "drheri_test_prelabel"
    monkeypatch.setattr(fiftyone_writer, "DATASET", ds_name)
    if ds_name in fo.list_datasets():
        fo.delete_dataset(ds_name)
    rec = {"content_hash": "h1", "path": "crop.png", "brand": "BEGO", "model": "SC",
           "diameter": "4.1", "length": None, "part_number": "58160",
           "ai_confidence": 0.4, "evidence": "SC", "source_page": 18,
           "bbox": [1, 2, 3, 4], "needs_review": True}
    n = fiftyone_writer.register_prelabeled([rec])
    assert n == 1
    ds = fo.load_dataset(ds_name)
    s = next(iter(ds))
    assert s["brand"] == "BEGO" and s["model"] == "SC" and s["diameter"] == "4.1"
    assert "needs_review" in s.tags
    # 멱등: 같은 hash 재등록은 0
    assert fiftyone_writer.register_prelabeled([rec]) == 0
    fo.delete_dataset(ds_name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_fiftyone_writer.py -v`
Expected: FAIL — `ModuleNotFoundError: ...labeling.fiftyone_writer` (fiftyone 미설치면 SKIP)

- [ ] **Step 3: Implement fiftyone_writer.py**

```python
"""미리라벨 크롭을 FiftyOne 'drheri' 데이터셋에 증분 등록.

기존 review.py 의 증분 등록 관례를 따르되 라벨 필드/needs_review 태그를 채운다.
등록 후엔 기존 sync(keep/reject)·promote 흐름이 그대로 처리한다."""
from __future__ import annotations

from .. import storage

DATASET = "drheri"

_STR_FIELDS = ["content_hash", "brand", "model", "diameter", "length",
               "part_number", "evidence", "modality", "stage", "source_id", "origin_url"]


def register_prelabeled(records: list[dict], log=print) -> int:
    if not records:
        return 0
    try:
        import fiftyone as fo
    except Exception as e:  # noqa: BLE001
        log(f"[fiftyone_writer] FiftyOne 미설치 — 등록 생략 ({e})")
        return 0

    if DATASET in fo.list_datasets():
        ds = fo.load_dataset(DATASET)
    else:
        ds = fo.Dataset(DATASET, persistent=True)
        for f in _STR_FIELDS:
            ds.add_sample_field(f, fo.StringField)
        ds.add_sample_field("ai_confidence", fo.FloatField)
        ds.add_sample_field("source_page", fo.IntField)

    existing = set(ds.values("content_hash")) if len(ds) else set()
    samples = []
    for r in records:
        if r["content_hash"] in existing:
            continue
        s = fo.Sample(filepath=str((storage.DATA_ROOT / r["path"]).resolve()))
        for f in ["content_hash", "brand", "model", "diameter", "length",
                  "part_number", "evidence"]:
            s[f] = r.get(f)
        s["ai_confidence"] = float(r.get("ai_confidence") or 0.0)
        s["source_page"] = int(r.get("source_page") or 0)
        s["modality"] = "catalog"
        s["stage"] = "review"
        s["source_id"] = "catalog_vlm"
        s["origin_url"] = r.get("origin_url")
        if r.get("needs_review"):
            s.tags.append("needs_review")
        samples.append(s)
    if samples:
        ds.add_samples(samples)
    log(f"[fiftyone_writer] 미리라벨 등록 {len(samples)}장 (기존 {len(existing)})")
    return len(samples)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_fiftyone_writer.py -v`
Expected: PASS (또는 fiftyone 미설치 시 SKIP)

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/labeling/fiftyone_writer.py tests/test_fiftyone_writer.py
git commit -m "feat(labeling): 미리라벨 크롭 FiftyOne 증분 등록 + needs_review"
```

---

## Task 8: runner — PDF 1건 오케스트레이션

렌더 → 페이지 필터(검출 0개 스킵) → 픽스처 페이지 병렬(검출→마크→매핑→마스터 크롭→manifest→FiftyOne). content_hash 멱등. `needs_review` 규칙: confidence < 임계 또는 model/diameter 누락.

**Files:**
- Create: `drheri_pipeline/labeling/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `render.render_pdf`, `detect.detect_fixtures`/`to_master`, `mark.mark_page`, `mapper.map_specs`, `partnum.parse_length`, `fiftyone_writer.register_prelabeled`, `storage`
- Produces:
  - `@dataclass RunSummary: pdf:str; brand:str; pages:int; fixture_pages:int; crops:int; needs_review:int`
  - `label_catalog(pdf_url:str, brand:str, pages:str="", *, master_dpi=300, view_long_px=1024, conf_min=0.6, max_workers=4, log=print) -> RunSummary`

- [ ] **Step 1: Write the failing test** (모든 GPU 호출 monkeypatch — 순수 오케스트레이션 검증)

`tests/test_runner.py`:
```python
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
    def fake_detect(view, **kw):
        return [Box(0.5, (1, 1, 5, 5))] if getattr(fake_detect, "call", 0) == 0 or True else []
    calls = {"n": 0}
    def fake_detect2(view, **kw):
        calls["n"] += 1
        return [Box(0.5, (1, 1, 5, 5))] if calls["n"] == 1 else []
    monkeypatch.setattr(runner, "detect_fixtures", fake_detect2)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: ...labeling.runner`

- [ ] **Step 3: Implement runner.py**

```python
"""PDF 1건 라벨링 오케스트레이션 — 렌더·필터·병렬·크롭·manifest·FiftyOne."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO

from .. import storage
from ..taxonomy import normalize_brand
from .render import render_pdf
from .detect import detect_fixtures, to_master
from .mark import mark_page
from .mapper import map_specs
from .partnum import parse_length
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


def _process_page(page, brand, conf_min, log) -> list[dict]:
    """한 페이지 → 크롭 레코드 리스트 (검출 0개면 빈 리스트)."""
    view_boxes = detect_fixtures(page.view)
    if not view_boxes:
        return []
    marked = mark_page(page.view, view_boxes)
    specs = map_specs(marked, page.master, view_boxes, brand, page.text)
    recs: list[dict] = []
    seen: set[str] = set()
    for i, vb in enumerate(view_boxes):
        mb = to_master(vb, page.scale)
        crop = page.master.crop(mb.xyxy)
        buf = BytesIO(); crop.save(buf, "PNG"); png = buf.getvalue()
        chash = storage.content_hash(png)
        if chash in seen:
            continue
        seen.add(chash)
        sp = specs[i] if i < len(specs) else None
        model = sp.model if sp else None
        diameter = sp.diameter if sp else None
        length = (sp.length if sp and sp.length else
                  parse_length(brand, sp.part_number if sp else None))
        conf = sp.confidence if sp else 0.0
        needs = conf < conf_min or not model or not diameter
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
            "modality": "catalog", "source_id": "catalog_vlm", "source_type": "catalog_vlm",
            "source_page": page.page_no, "page_no": page.page_no,
            "bbox": list(mb.xyxy), "needs_review": needs,
            "brand_norm": normalize_brand(brand), "fetched_at": _now(),
        })
    return recs


def label_catalog(pdf_url: str, brand: str, pages: str = "", *, master_dpi: int = 300,
                  view_long_px: int = 1024, conf_min: float = 0.6,
                  max_workers: int = 4, log=print) -> RunSummary:
    pages_list = list(render_pdf(pdf_url, pages, master_dpi=master_dpi,
                                 view_long_px=view_long_px, log=log))
    all_recs: list[dict] = []
    fixture_pages = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for recs in ex.map(lambda p: _process_page(p, brand, conf_min, log), pages_list):
            if recs:
                fixture_pages += 1
                all_recs.extend(recs)
    storage.append_manifest(all_recs)
    register_prelabeled(all_recs, log=log)
    summ = RunSummary(pdf=pdf_url, brand=brand, pages=len(pages_list),
                      fixture_pages=fixture_pages, crops=len(all_recs),
                      needs_review=sum(1 for r in all_recs if r["needs_review"]))
    log(f"[runner] {brand} pages={summ.pages} fixture_pages={summ.fixture_pages} "
        f"crops={summ.crops} needs_review={summ.needs_review}")
    return summ
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/labeling/runner.py tests/test_runner.py
git commit -m "feat(labeling): PDF 라벨링 오케스트레이터(필터·병렬·크롭·manifest)"
```

---

## Task 9: cli — label_catalog 엔트리포인트

`python -m drheri_pipeline.labeling.cli --pdf X --brand Y --pages 12-26` 로 실행. NAS 파일 경로/URL 모두 그대로 `pdf_url` 로 흐른다.

**Files:**
- Create: `drheri_pipeline/labeling/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `runner.label_catalog`
- Produces: `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from drheri_pipeline.labeling import cli
from drheri_pipeline.labeling.runner import RunSummary


def test_cli_parses_and_invokes_runner(monkeypatch):
    got = {}
    def fake_run(pdf_url, brand, pages="", **kw):
        got.update(pdf=pdf_url, brand=brand, pages=pages, kw=kw)
        return RunSummary(pdf_url, brand, 1, 1, 2, 0)
    monkeypatch.setattr(cli, "label_catalog", fake_run)
    rc = cli.main(["--pdf", "/nas/BEGO/x.pdf", "--brand", "BEGO", "--pages", "12-26",
                   "--conf-min", "0.5"])
    assert rc == 0
    assert got["pdf"] == "/nas/BEGO/x.pdf" and got["brand"] == "BEGO"
    assert got["pages"] == "12-26" and got["kw"]["conf_min"] == 0.5


def test_cli_requires_pdf_and_brand():
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["--pdf", "x.pdf"])   # brand 누락
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: ...labeling.cli`

- [ ] **Step 3: Implement cli.py**

```python
"""label_catalog CLI — 카탈로그 PDF(URL 또는 NAS 파일) 1건 라벨링."""
from __future__ import annotations

import argparse

from .runner import label_catalog


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="label_catalog")
    ap.add_argument("--pdf", required=True, help="PDF URL 또는 로컬/NAS 파일 경로")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--pages", default="", help='예: "12-26, 30" (비우면 전체)')
    ap.add_argument("--master-dpi", type=int, default=300)
    ap.add_argument("--view-long-px", type=int, default=1024)
    ap.add_argument("--conf-min", type=float, default=0.6)
    ap.add_argument("--max-workers", type=int, default=4)
    a = ap.parse_args(argv)
    summ = label_catalog(a.pdf, a.brand, a.pages, master_dpi=a.master_dpi,
                         view_long_px=a.view_long_px, conf_min=a.conf_min,
                         max_workers=a.max_workers)
    print(summ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite (회귀 확인)**

Run: `cd data-pipeline && python -m pytest -q`
Expected: PASS (기존 + 신규 전부)

- [ ] **Step 6: Commit**

```bash
git add drheri_pipeline/labeling/cli.py tests/test_cli.py
git commit -m "feat(labeling): label_catalog CLI 엔트리포인트"
```

---

## Task 10: DGX 배치 — NAS 마운트·GPU 서비스·FiftyOne·스모크

DGX(sh_lee)에서 실제로 돌린다. NAS 읽기전용 마운트, GDINO 서비스 기동(GPU 컨테이너), FiftyOne+Mongo, 그리고 BEGO 실측 스모크. 코드가 아니라 **검증된 절차 문서 + 스모크 실행**이 산출물.

**Files:**
- Create: `docs/DGX_LABELING_DEPLOY.md`
- Depends on: Tasks 1–9 (엔진·서비스·CLI)

**필요 입력(착수 시 사용자에게):** NAS `//172.30.1.8/nas-metass` 마운트 계정/비번.

- [ ] **Step 1: NAS 읽기전용 마운트** (인증정보 수령 후)

```bash
sudo mkdir -p /mnt/nas-metass
# 자격증명은 root 전용 파일로 (셸 히스토리·평문 노출 방지)
sudo bash -c 'umask 077; cat > /etc/cifs-nas-metass <<EOF
username=<NAS_USER>
password=<NAS_PASS>
EOF'
sudo mount -t cifs "//172.30.1.8/nas-metass" /mnt/nas-metass \
  -o credentials=/etc/cifs-nas-metass,ro,iocharset=utf8,vers=3.0
ls "/mnt/nas-metass/03. Dr.HERi/02. 카탈로그/BEGO/"   # PDF 보이면 성공
```
검증: BEGO 폴더의 PDF 목록이 보인다.

- [ ] **Step 2: GDINO 서비스 기동 (GPU 컨테이너 안, 웜 유지)**

기존 `vllm-shlee` 컨테이너에 fastapi/uvicorn 이 없으면 설치 후 서비스 기동:
```bash
sudo docker exec -d vllm-shlee bash -lc \
  'pip install -q fastapi uvicorn && cd /work && python scripts/gdino_server.py'
# 헬스체크 (호스트에서)
curl -s -X POST http://127.0.0.1:8100/detect \
  -d "{\"image_b64\":\"$(base64 -w0 /home/sh_lee/bego_p18_1024.png)\",\"prompt\":\"a gray implant object\",\"threshold\":0.3}" \
  -H 'Content-Type: application/json' | head -c 300
```
검증: `boxes` 에 5개 근처(스펙 §9 실측 5/5) 반환. (컨테이너에 `scripts/` 가 없으면 `docker cp` 로 넣거나 리포를 마운트.)

- [ ] **Step 3: 엔진 venv + FiftyOne/Mongo (DGX 호스트)**

```bash
cd /home/sh_lee/Dr.HERi/data-pipeline     # git pull 로 배포
python3.11 -m venv .venv && . .venv/bin/activate
uv pip install -e ".[dev]"                # 코어(fiftyone 포함), torch/transformers 불필요
# FiftyOne 최초 실행이 자체 mongod(ARM) 를 받아 기동 — AVX 무관(§3)
python -c "import fiftyone as fo; print(fo.list_datasets())"
```
검증: FiftyOne import·mongod 기동 성공(에러 없이 데이터셋 목록 출력).

- [ ] **Step 4: BEGO 스모크 (end-to-end 실측)**

```bash
export DATA_ROOT=/home/sh_lee/drheri-data
python -m drheri_pipeline.labeling.cli \
  --pdf "/mnt/nas-metass/03. Dr.HERi/02. 카탈로그/BEGO/BEGO-2018.pdf" \
  --brand BEGO --pages 18
```
검증(스펙 §9 기대): `RunSummary(... fixture_pages=1 crops≈5 ...)`. `manifest.jsonl` 에 크롭 레코드, `DATA_ROOT/review/BEGO/.../catalog/*.png` 에 **고해상도** 크롭 생성. 처리시간 로그가 페이지당 수십 초 이내.

- [ ] **Step 5: FiftyOne 검수 확인**

```bash
python scripts/serve_fiftyone_service.py    # 기존 스크립트 재사용 (없으면 fo.launch_app)
```
검증: 브라우저(LAN)에서 `drheri` 데이터셋에 BEGO 크롭이 뜨고, `brand/model/diameter/length` 필드가 **미리 채워져** 있으며 저confidence 건에 `needs_review` 태그가 붙어 있다. 라벨 수정·keep/reject 가 동작한다(기존 sync 흐름).

- [ ] **Step 6: 배치 문서화 + 커밋**

`docs/DGX_LABELING_DEPLOY.md` 에 위 절차(마운트·서비스·venv·스모크·검수)와 서비스 상시화(systemd 또는 `docker exec -d`) 방법을 정리.
```bash
git add docs/DGX_LABELING_DEPLOY.md
git commit -m "docs: DGX 라벨링 엔진 배치 절차 + BEGO 스모크"
```

---

## Self-Review

**1. Spec coverage:**
- §3 배치(DGX 통합) → Task 10. 검수 substrate(Mongo+FiftyOne) → Task 10 Step 3/5. 입력(URL/NAS 파일) → Task 1(pdf_util)·Task 9(CLI)·Task 10 Step 4. 검출(GDINO 시각프롬프트) → Task 4. 매핑(set-of-mark 하이브리드) → Task 6. 저장(로컬, NAS 읽기전용) → Task 8/10. 오케스트레이션(CLI+원장) → Task 8(manifest 멱등)·Task 9.
- §4 데이터흐름 → Task 8 runner 가 필터·병렬·크롭·등록 전부 구현.
- §5 구성단위 8개 → Task 1(source_resolver=pdf_util)·2(renderer)·4(detector)·6(mapper)·3(partnum)·7(writer)·8(runner+ledger=manifest)·9(cli). 전부 매핑됨.
- §6 라벨 스키마·granularity → Task 7 필드 + Task 8 length 규칙(sp.length 우선, 없으면 part_number, 못 찾으면 None — "여러 길이 복제 금지" 준수).
- §7 성능(페이지필터·병렬·웜·이원해상도) → Task 8(_process_page 검출0 스킵·ThreadPoolExecutor)·Task 2(이원렌더)·Task 4/10(웜 서비스).
- §8 에러(렌더실패 스킵·검출0 스킵·VLM실패 needs_review·멱등) → Task 6(try/except)·Task 8(멱등·needs_review)·Task 2. **갭 보완**: 렌더 개별 페이지 예외 격리는 runner `_process_page` 를 try 로 감싸는 것으로 충분 — Task 8 구현 시 `ex.map` 결과가 예외면 그 페이지만 건너뛰도록 `_process_page` 최상단을 `try/except` 로 감싼다(가이드: 실패 페이지는 빈 리스트 반환·로그).
- §9 테스트/호출규약 → 각 Task TDD + Task 4 gdino_server·Task 6 mapper 가 검증된 규약 사용. 통합 스모크 → Task 10 Step 4.
- §10 인프라(vLLM 재사용·GDINO 서비스·Mongo/FiftyOne·NAS ro) → Task 4·10.

**2. Placeholder scan:** "TODO/TBD" 없음. Task 2 Step 3 의 `pdf_util_import` 줄은 착오 방지 주석으로 명시 제거 지시함. Task 8 §8 갭 보완 지침을 명문화(빈 리스트 반환).

**3. Type consistency:** `Box(score,xyxy)` — detect/mark/mapper/runner 일관. `BoxSpec(index,model,diameter,length,part_number,confidence,evidence)` — mapper/runner 일관. `RenderedPage(page_no,master,view,scale,text)` — render/runner 일관. `register_prelabeled(records,log)` — writer/runner 일관. 레코드 dict 키(content_hash,path,brand,model,diameter,length,part_number,ai_confidence,evidence,source_page,bbox,needs_review) — runner 생성 ↔ writer 소비 일치.

**갭 보완 반영:** Task 8 Step 3 구현 시 `_process_page` 를 try/except 로 감싸 페이지 단위 예외 격리(§8). runner 코드의 `_process_page` 상단에 다음을 추가한다:
```python
def _process_page(page, brand, conf_min, log):
    try:
        return _process_page_inner(page, brand, conf_min, log)   # 위 본문을 _inner 로
    except Exception as e:  # noqa: BLE001
        log(f"[runner] page {page.page_no} 실패 — 건너뜀 ({e})")
        return []
```
(테스트 `test_runner.py` 는 정상경로만 검증하므로 이 래핑으로 깨지지 않는다.)
