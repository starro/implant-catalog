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
