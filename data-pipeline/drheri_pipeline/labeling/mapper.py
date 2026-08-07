"""Qwen3-VL(vLLM) 스펙 매퍼 — set-of-mark 1콜.

각 픽스처 렌더에 번호 박스를 그려 보내고, 번호별 스펙을 1콜로 받는다.
전략(2026-08-08 DGX 스모크 반영): 배치 결과를 index 로 박스에 정렬해 채우고(0/1-based 자동보정),
스펙이 안 온 박스는 null+needs_review 로 남긴다. 예전의 '박스별 크롭 개별콜' fallback 은
스펙표 페이지에서 표 맥락을 잃어 역효과라 제거 — 배치가 완전 실패(0행)일 때만 full-page 1회 재시도."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from io import BytesIO

import httpx

_URL = "http://127.0.0.1:8000/v1/chat/completions"

_SYS = ("You label dental implant catalog pages. Return ONLY a JSON array, no prose. "
        "The image has red boxes each with a number; each box outlines ONE rendered "
        "implant fixture. Look at the fixture INSIDE each numbered box and find ITS row "
        "in the page's spec table, then report that row's spec for that box.")
_PROMPT = ('There are exactly {n} numbered red boxes (0..{last}). Return a JSON array of '
           'EXACTLY {n} objects, one per box, using that box number as "index" (0-based). '
           'Include every box even if unsure (use nulls). Each object: '
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
                   confidence=float(d.get("confidence") or 0.0),
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


def _by_index(rows: list[dict], n: int) -> dict[int, dict]:
    """행들을 box index(0-based)로 정렬. VLM 이 1-based 로 매기면 자동으로 0-base 보정."""
    idxs = []
    for r in rows:
        try:
            idxs.append(int(r["index"]))
        except (KeyError, TypeError, ValueError):
            idxs.append(None)
    present = [i for i in idxs if i is not None]
    # 0 이 없고 전부 1..n 범위면 1-based 로 보고 -1 시프트
    shift = 1 if present and 0 not in present and min(present) == 1 and max(present) <= n else 0
    out: dict[int, dict] = {}
    for r, i in zip(rows, idxs):
        if i is None:
            continue
        out[i - shift] = r
    return out


def map_specs(marked_view, master, boxes, brand, page_text, *,
              url: str = _URL, model_name: str = "qwen3vl") -> list[BoxSpec]:
    if not boxes:
        return []
    text = _PROMPT.format(n=len(boxes), last=len(boxes) - 1, brand=brand,
                          page_text=(page_text or "")[:2000])
    try:
        rows = _call(marked_view, text, url, model_name)
    except Exception:
        rows = []
    if not rows:                                   # 배치 완전 실패 → full-page 1회 재시도
        try:
            rows = _call(marked_view, text, url, model_name)
        except Exception:
            rows = []
    by_index = _by_index(rows, len(boxes))
    # 스펙이 안 온 박스는 null 로 남긴다(→ 크롭·번호 순으로 index 부여). 개별 크롭콜은 안 한다.
    return [_spec({**by_index[i], "index": i}) if i in by_index
            else _spec({"index": i, "confidence": 0.0})
            for i in range(len(boxes))]
