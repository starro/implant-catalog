"""set-of-mark — 이미지에 번호 박스를 그린다(VLM 이 번호로 스펙 응답).

번호는 크고 대비 높게(흰 글자 + 빨강 배지) — 고해상도 페이지에서 VLM 이 실제로 읽어야
박스↔스펙 정렬이 된다. 번호가 안 보이면 VLM 이 표 행만 나열하고 위치 grounding 을 놓친다."""
from __future__ import annotations


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)   # Pillow ≥10.1: 크기 지정 가능
    except TypeError:
        return ImageFont.load_default()            # 구버전 폴백(고정 크기)


def mark_page(view_img, boxes):
    from PIL import ImageDraw
    out = view_img.copy()
    draw = ImageDraw.Draw(out)
    badge = max(18, out.width // 55)               # 해상도 비례 배지 크기
    font = _font(badge)
    for i, b in enumerate(boxes):
        x1, y1, x2, y2 = b.xyxy
        draw.rectangle((x1, y1, x2, y2), outline=(255, 0, 0), width=3)
        label = str(i)
        tw, th = badge, badge + 4
        bx = x1
        by = max(0, y1 - th)                        # 박스 위, 없으면 안쪽
        draw.rectangle((bx, by, bx + tw + 6, by + th), fill=(255, 0, 0))
        draw.text((bx + 3, by), label, fill=(255, 255, 255), font=font)
    return out
