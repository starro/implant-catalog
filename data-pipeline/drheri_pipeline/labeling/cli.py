"""label_catalog CLI — 카탈로그 PDF(URL 또는 NAS 파일) 1건 라벨링."""
from __future__ import annotations

import argparse

from .runner import label_catalog


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="label_catalog")
    ap.add_argument("--pdf", required=True, help="PDF URL 또는 로컬/NAS 파일 경로")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--pages", default="", help='예: "12-26, 30" (비우면 전체)')
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--conf-min", type=float, default=0.6)
    ap.add_argument("--max-workers", type=int, default=4)
    a = ap.parse_args(argv)
    summ = label_catalog(a.pdf, a.brand, a.pages, dpi=a.dpi, conf_min=a.conf_min,
                         max_workers=a.max_workers)
    print(summ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
