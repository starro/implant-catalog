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

_SYS = ("You identify dental implant fixtures on a catalog OR manual page. Return ONLY a JSON "
        "array, no prose. You get the page IMAGE (red numbered boxes mark detected objects) and "
        "the page TEXT. Use ALL available page context to label each numbered box — a heading, a "
        "caption, a size printed next to a render, a spec table IF one exists, or surrounding "
        "prose. The page MAY OR MAY NOT have a spec table; do NOT assume one — read whatever "
        "context is nearest and most relevant to each box. Look at the object INSIDE each box; "
        "different boxes usually show different diameters. Also judge is_fixture: false when the "
        "boxed object is not actually an implant fixture (a diagram, tool, x-ray, or illustration).")
_PROMPT = ('There are exactly {n} numbered red boxes (0..{last}). Box vertical positions '
           '(top=0%, bottom=100%): {positions}. A render is usually placed at the SAME height '
           'as its own group of rows in a table — use each box\'s vertical position to find the '
           'rows at that height and read THAT group\'s value. Return a JSON array of EXACTLY {n} '
           'objects, one per box (index 0-based). For each box give what the context states: '
           'model/series (often in a heading/title), diameter (each render usually represents '
           'one diameter family), length (null — a render spans many lengths — unless the box '
           'clearly maps to a single length), part_number. Use null for anything not stated; do '
           'NOT just list table rows top-to-bottom. Each object: '
           '{{"index":int,"is_fixture":bool,"model":str|null,"diameter":str|null,'
           '"length":str|null,"part_number":str|null,"confidence":0..1,"evidence":str}}. '
           'is_fixture=false for non-fixtures (diagram/tool/x-ray/illustration). Give an HONEST '
           'confidence 0..1 — do NOT always answer 1; lower it when the box is not a clear '
           'fixture or the label is uncertain. Brand is {brand}. Page text:\n{page_text}')


@dataclass
class BoxSpec:
    index: int
    model: str | None
    diameter: str | None
    length: str | None
    part_number: str | None
    confidence: float
    evidence: str
    is_fixture: bool | None = None    # VLM 판단(픽스처 아님이면 False) — 버리진 않고 검수 필터용


def _b64(img) -> str:
    buf = BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


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


def _spec(d: dict) -> BoxSpec:
    return BoxSpec(index=int(d.get("index", 0)), model=d.get("model"),
                   diameter=d.get("diameter"), length=d.get("length"),
                   part_number=d.get("part_number"),
                   confidence=float(d.get("confidence") or 0.0),
                   evidence=(d.get("evidence") or "")[:300],
                   is_fixture=_as_bool(d.get("is_fixture")))


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
    h = getattr(marked_view, "height", 0) or 1
    positions = ", ".join(
        f"box {i}={round((b.xyxy[1] + b.xyxy[3]) / 2 / h * 100)}%" for i, b in enumerate(boxes))
    text = _PROMPT.format(n=len(boxes), last=len(boxes) - 1, positions=positions,
                          brand=brand, page_text=(page_text or "")[:2000])
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
