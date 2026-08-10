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


# 프롬프트 규칙(DGX 실측):
#  - 끝의 마침표는 필수(제거 금지). Grounding DINO 는 period-terminated 쿼리 관례라
#    마침표 없으면 리콜 붕괴(BEGO p18: "…fixture" 0개 vs "…fixture." 5개).
#  - 색을 넣지 않는다("gray" 편향은 실버 픽스처를 놓친다).
#  - "a dental implant." 채택: "an implant fixture." 는 3D 렌더된 큰 픽스처엔 강하나 카탈로그
#    표의 작은 도식 썸네일을 놓쳤다(Hiossen NH p3: 썸네일 점수 ~0.15). "a dental implant." 는
#    같은 썸네일을 ~0.4 로 인식 → 0.3 에서 직경 변형별로 검출(3개→10개). 큰 픽스처(0.63)도 유지.
def detect_fixtures(image, *, url: str = "http://127.0.0.1:8100/detect",
                    prompt: str = "a dental implant.", threshold: float = 0.3) -> list[Box]:
    resp = httpx.post(url, json={"image_b64": _png_b64(image),
                                 "prompt": prompt, "threshold": threshold}, timeout=60)
    resp.raise_for_status()
    return [Box(score=float(b["score"]), xyxy=tuple(int(v) for v in b["xyxy"]))
            for b in resp.json()["boxes"]]
