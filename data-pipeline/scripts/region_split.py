"""임플란트 fixture 부위 3등분 PoC — 장축 따라 coronal/body/apex 영역을 FiftyOne 에 표시.

모델 없이 기하학적으로:
  전경(implant) 마스크(Otsu, 배경밝기 자동판별) → 최대 연결성분 → PCA 장축
  → 장축 투영을 3등분 → 부위별 axis-aligned bbox → FiftyOne Detections('regions').

coronal/apex 방향: 양끝 세그먼트 centroid 의 y 로 추정(위=coronal). 휴리스틱.
대상: review/training 의 이미지(catalog 렌더 + xray). 모델 단계로 가기 전 개념 검증용.

실행: bash scripts/region_split.py  (또는 python scripts/region_split.py [limit])
"""
import glob
import sys

import numpy as np
from PIL import Image
import fiftyone as fo

from drheri_pipeline import storage

DATASET = "implant_regions"
NAMES = ["coronal", "body", "apex"]


def _otsu(gray: np.ndarray) -> int:
    hist, _ = np.histogram(gray, bins=256, range=(0, 255))
    total = gray.size
    sum_all = np.dot(np.arange(256), hist)
    sumB = wB = 0.0
    max_var = thr = 0
    for t in range(256):
        wB += hist[t]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sumB += t * hist[t]
        mB = sumB / wB
        mF = (sum_all - sumB) / wF
        var = wB * wF * (mB - mF) ** 2
        if var > max_var:
            max_var = var
            thr = t
    return thr


def _largest_component(mask: np.ndarray) -> np.ndarray:
    try:
        from scipy import ndimage
        lbl, n = ndimage.label(mask)
        if n <= 1:
            return mask
        sizes = ndimage.sum(mask, lbl, range(1, n + 1))
        return lbl == (int(np.argmax(sizes)) + 1)
    except Exception:
        return mask  # scipy 없으면 전체 마스크 사용


def regions_for(path: str):
    g = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
    H, W = g.shape
    thr = _otsu(g)
    border = np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]])
    bg_bright = border.mean() > thr
    mask = (g < thr) if bg_bright else (g > thr)   # 배경 반대편 = 전경(implant)
    mask = _largest_component(mask)

    ys, xs = np.nonzero(mask)
    if len(xs) < 50:
        return []
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    c = pts.mean(0)
    cov = np.cov((pts - c).T)
    evals, evecs = np.linalg.eigh(cov)
    axis = evecs[:, int(np.argmax(evals))]       # 장축 단위벡터
    proj = (pts - c) @ axis
    lo, hi = proj.min(), proj.max()
    if hi - lo < 1e-6:
        return []
    t1, t2 = lo + (hi - lo) / 3, lo + 2 * (hi - lo) / 3
    segs = [proj < t1, (proj >= t1) & (proj < t2), proj >= t2]

    # coronal 쪽 결정: 양끝 세그먼트 중 y 평균 작은(위) 쪽이 coronal
    y0m = ys[segs[0]].mean() if segs[0].any() else 0
    y2m = ys[segs[2]].mean() if segs[2].any() else 0
    names = NAMES if y0m <= y2m else NAMES[::-1]

    dets = []
    for seg, name in zip(segs, names):
        if not seg.any():
            continue
        sx, sy = xs[seg], ys[seg]
        x0, x1, y0, y1 = sx.min(), sx.max(), sy.min(), sy.max()
        dets.append(fo.Detection(
            label=name,
            bounding_box=[x0 / W, y0 / H, (x1 - x0 + 1) / W, (y1 - y0 + 1) / H],
        ))
    return dets


def main():
    import os
    limit = next((int(a) for a in sys.argv[1:] if a.isdigit()), 0)
    src = os.getenv("REGION_SRC")   # 임의 디렉토리 지정 (예: DGX 에서 가져온 깔끔한 fixture)
    files = []
    if src:
        for ext in ("png", "jpg", "jpeg"):
            files += glob.glob(os.path.join(src, "**", f"*.{ext}"), recursive=True)
    else:
        for sub in ("training", "review"):
            for ext in ("png", "jpg", "jpeg"):
                files += glob.glob(str(storage.DATA_ROOT / sub / "**" / f"*.{ext}"), recursive=True)
    files = sorted(set(files))
    if limit:
        files = files[:limit]
    print(f"대상 이미지: {len(files)}장")

    if DATASET in fo.list_datasets():
        fo.delete_dataset(DATASET)
    ds = fo.Dataset(DATASET, persistent=True)
    samples = []
    for f in files:
        s = fo.Sample(filepath=f)
        try:
            s["regions"] = fo.Detections(detections=regions_for(f))
        except Exception as e:  # noqa: BLE001
            print(f"  skip {f}: {e}")
            s["regions"] = fo.Detections(detections=[])
        samples.append(s)
    ds.add_samples(samples)
    print(f"count: {ds.count()}  | regions 라벨: {ds.count_values('regions.detections.label')}")

    if "--build-only" not in sys.argv:
        session = fo.launch_app(ds, port=5151)
        session.wait(-1)


if __name__ == "__main__":
    main()
