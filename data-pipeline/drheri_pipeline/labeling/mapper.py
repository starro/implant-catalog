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
