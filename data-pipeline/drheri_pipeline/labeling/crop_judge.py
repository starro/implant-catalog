"""개별 크롭 is_fixture 판단 — set-of-mark(mapper.py)의 대안.

set-of-mark 는 조밀한 카탈로그 페이지(박스 20+개)에서 8B 가 번호↔영역 grounding 에
실패해 is_fixture 를 통째로 못 낸다(실측 Hiossen NH p3: 0/27). 대신 박스마다 크롭 1개를
'이거 픽스처냐?' 단순질문으로 물으면 grounding 부담이 사라져 27/27 응답(실측)하고 더 빠르다.

읽기(모델/지름/길이/코드)는 여기서 안 한다 — 그건 텍스트/좌표(heading_model, geom,
partnum_geom)로 뽑는다. 이 모듈은 VLM 이 잘하는 '시각 판단(is_fixture)'만 맡는다."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from io import BytesIO

import httpx

_URL = "http://127.0.0.1:8000/v1/chat/completions"

_SYS = ("You judge ONE image: is it a dental implant FIXTURE (the screw-shaped, threaded "
        "titanium implant body that goes into bone)? Return ONLY JSON. NOT a fixture: "
        "abutments/tools/drivers, diagrams, x-rays, logos, text, tables, packaging.")
_USR = ('Is the object in this image a dental implant fixture? Return ONLY '
        '{"is_fixture": true|false, "confidence": 0.0-1.0}. Be HONEST with confidence.')


@dataclass
class FixtureJudge:
    is_fixture: bool | None
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


def _parse(content: str) -> FixtureJudge:
    """VLM 응답 텍스트에서 {is_fixture, confidence} JSON 추출. 실패 시 None 판단."""
    st, en = content.find("{"), content.rfind("}")
    if st < 0 or en <= st:
        return FixtureJudge(None, 0.0)
    try:
        d = json.loads(content[st:en + 1])
    except (ValueError, TypeError):
        return FixtureJudge(None, 0.0)
    return FixtureJudge(_as_bool(d.get("is_fixture")), float(d.get("confidence") or 0.0))


def _b64(img) -> str:
    buf = BytesIO(); img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _call(crop, url, model_name) -> FixtureJudge:
    body = {"model": model_name, "temperature": 0, "max_tokens": 80,
            "messages": [{"role": "system", "content": _SYS},
                         {"role": "user", "content": [
                             {"type": "text", "text": _USR},
                             {"type": "image_url", "image_url": {"url": _b64(crop)}}]}]}
    resp = httpx.post(url, json=body, timeout=60)
    resp.raise_for_status()
    return _parse(resp.json()["choices"][0]["message"]["content"])


def judge_fixtures(image, boxes, *, url: str = _URL,
                   model_name: str = "qwen3vl") -> list[FixtureJudge]:
    """각 박스를 크롭해 is_fixture 를 개별 판단(박스 순서대로). 콜 실패는 None 판단으로 격리."""
    out: list[FixtureJudge] = []
    for b in boxes:
        try:
            out.append(_call(image.crop(b.xyxy), url, model_name))
        except Exception:   # noqa: BLE001 — 크롭 1개 실패가 페이지를 멈추지 않게
            out.append(FixtureJudge(None, 0.0))
    return out
