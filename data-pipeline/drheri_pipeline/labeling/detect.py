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
