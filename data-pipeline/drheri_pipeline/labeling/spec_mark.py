"""단일 마크 스펙 추출 — 박스 1개만 마크한 풀페이지를 VLM 에 주고 그 픽스처의 스펙을 받는다.

set-of-mark(마크 다수)는 8B 가 번호↔영역 grounding 에 실패한다(실측 0/27). 마크를 1개로 줄이면
grounding 부담이 사라져, VLM 이 잘하는 '읽기'로 그 렌더의 표 행을 읽는다. 실측(Hiossen NH p3):
지름 정확, 길이 대부분 정확, 코드까지. 크롭 is_fixture + 좌표추출을 대체하는 통합 콜 —
is_fixture 도 같은 콜에서 판단한다(풀페이지라 맥락으로 픽스처 여부도 봄)."""
from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO

import httpx

from .mark import mark_page

_URL = "http://127.0.0.1:8000/v1/chat/completions"

# 페이지 안에서 박스별 콜을 동시에 돌리는 수(콜이 I/O 대기라 스레드로 효과). runner 의 페이지
# 병렬(4)과 곱해져 총 동시 VLM 요청 ≈ 4×이 값 — 공유 GPU 부하 고려한 보수값.
SPEC_WORKERS = 3

_SYS = ("You read a dental implant catalog page. Exactly ONE implant render is marked with a red "
        "numbered box (0). Judge and read ONLY that marked implant, using the spec table row or "
        "text nearest the marked render. Return ONLY JSON, no prose.")
_USR = ('Return the spec of the marked implant (red box 0) as JSON: '
        '{{"is_fixture": true|false, "model": str|null, "diameter": str|null, "length": str|null, '
        '"code": str|null, "confidence": 0.0-1.0}}. is_fixture=false if the marked object is NOT an '
        'implant fixture (abutment, tool/driver, diagram, x-ray, logo, illustration). Read '
        'diameter/length/code from the row/text nearest the marked render; use null if not printed. '
        'model = product series/line (often the page title). Brand is {brand}. Give an HONEST '
        'confidence — lower it when the marked object is unclear or the values are uncertain.')


@dataclass
class MarkSpec:
    is_fixture: bool | None
    model: str | None
    diameter: str | None
    length: str | None
    part_number: str | None
    confidence: float
    evidence: str = ""


def _as_bool(v) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "y", "1"):
            return True
        if s in ("false", "no", "n", "0"):
            return False
    return None


def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _num(v) -> str | None:
    """지름/길이 정규화 — 'F 6.0', '3.2mm', 'Ø4.5' → '6.0'/'3.2'/'4.5'. 숫자 없으면 None."""
    s = _s(v)
    if s is None:
        return None
    s = s.replace("mm", "").replace("Ø", "").replace("ø", "").replace("F", "").replace("Φ", "").strip()
    return s or None


def _parse(content: str) -> MarkSpec:
    st, en = content.find("{"), content.rfind("}")
    if st < 0 or en <= st:
        return MarkSpec(None, None, None, None, None, 0.0)
    try:
        d = json.loads(content[st:en + 1])
    except (ValueError, TypeError):
        return MarkSpec(None, None, None, None, None, 0.0)
    return MarkSpec(
        is_fixture=_as_bool(d.get("is_fixture")),
        model=_s(d.get("model")),
        diameter=_num(d.get("diameter")),
        length=_num(d.get("length")),
        part_number=_s(d.get("code")),
        confidence=float(d.get("confidence") or 0.0),
    )


def _b64(img) -> str:
    buf = BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _call(marked, brand, url, model_name) -> MarkSpec:
    body = {"model": model_name, "temperature": 0, "max_tokens": 160,
            "messages": [{"role": "system", "content": _SYS},
                         {"role": "user", "content": [
                             {"type": "text", "text": _USR.format(brand=brand)},
                             {"type": "image_url", "image_url": {"url": _b64(marked)}}]}]}
    resp = httpx.post(url, json=body, timeout=90)
    resp.raise_for_status()
    return _parse(resp.json()["choices"][0]["message"]["content"])


def spec_for_boxes(image, boxes, brand, *, url: str = _URL,
                   model_name: str = "qwen3vl", workers: int = SPEC_WORKERS) -> list[MarkSpec]:
    """각 박스를 '그 박스만 마크한 풀페이지'로 VLM 에 물어 스펙을 받는다(입력 박스 순서 보존).

    박스별 콜을 workers 개까지 동시에 돌려 페이지 처리를 단축한다(콜이 I/O 대기라 스레드로 효과).
    콜 실패는 빈 스펙(None)으로 격리해 한 박스 실패가 페이지를 멈추지 않게 한다."""
    def one(b) -> MarkSpec:
        try:
            return _call(mark_page(image, [b]), brand, url, model_name)
        except Exception:   # noqa: BLE001
            return MarkSpec(None, None, None, None, None, 0.0)
    if workers <= 1 or len(boxes) <= 1:
        return [one(b) for b in boxes]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, boxes))   # map 은 입력 순서를 보존한다
