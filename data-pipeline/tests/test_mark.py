from PIL import Image
from drheri_pipeline.labeling import mark
from drheri_pipeline.labeling.detect import Box


def test_mark_page_returns_copy_same_size():
    img = Image.new("RGB", (100, 100), "white")
    boxes = [Box(0.5, (10, 10, 40, 40)), Box(0.5, (50, 50, 90, 90))]
    out = mark.mark_page(img, boxes)
    assert out.size == img.size
    assert out is not img                      # 원본 불변
    assert list(img.getdata()) == list(Image.new("RGB", (100, 100), "white").getdata())


def test_mark_page_empty_boxes():
    img = Image.new("RGB", (20, 20), "white")
    out = mark.mark_page(img, [])
    assert out.size == (20, 20)
