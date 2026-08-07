"""Grounding DINO HTTP 서비스 클라이언트."""
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


# 프롬프트 끝의 마침표는 필수(제거 금지) — Grounding DINO 는 period-terminated 쿼리 관례라
# 마침표가 없으면 리콜이 붕괴한다(BEGO p18 실측: "…object" 0개 vs "…object." 5개, thr 0.3).
def detect_fixtures(image, *, url: str = "http://127.0.0.1:8100/detect",
                    prompt: str = "a gray implant object.", threshold: float = 0.3) -> list[Box]:
    resp = httpx.post(url, json={"image_b64": _png_b64(image),
                                 "prompt": prompt, "threshold": threshold}, timeout=60)
    resp.raise_for_status()
    return [Box(score=float(b["score"]), xyxy=tuple(int(v) for v in b["xyxy"]))
            for b in resp.json()["boxes"]]
