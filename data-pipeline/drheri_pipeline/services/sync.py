"""FiftyOne 검수결과 → SQLite 반영 (수동 실행).

검수자는 FiftyOne 에서 두 가지를 한다.
  1) 태그로 판정: keep / reject
  2) 라벨 직접 수정: brand / series / surface / model

이 모듈이 한 번에 처리하는 것: 판정 반영 → 라벨 반영 → 승급(training) → 파일 이동.
버림은 삭제가 아니라 data/rejected/ 로 이동한다(오판 복구 가능).
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from drheri_pipeline import storage
from drheri_pipeline.db import conn
from drheri_pipeline.taxonomy import normalize_brand

DATASET = "drheri"
LABEL_FIELDS = ("brand", "series", "surface", "model")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank(v) -> bool:
    return not v or str(v).strip() in ("", "_unknown")


def read_review_state() -> list[dict]:
    """FiftyOne 데이터셋에서 태그와 라벨을 읽어온다. 미설치/데이터셋 없으면 빈 리스트."""
    try:
        import fiftyone as fo
    except Exception:  # noqa: BLE001
        return []
    if DATASET not in fo.list_datasets():
        return []
    ds = fo.load_dataset(DATASET)
    out = []
    for s in ds.select_fields(["content_hash", "tags", *LABEL_FIELDS]):
        out.append({"content_hash": s["content_hash"], "tags": list(s.tags or []),
                    **{f: s[f] for f in LABEL_FIELDS}})
    return out


def push_stage_to_fiftyone(moves: dict[str, str]) -> None:
    """승급/버림으로 파일이 이동한 샘플의 filepath 와 stage 를 갱신 (증분, 재빌드 아님)."""
    if not moves:
        return
    try:
        import fiftyone as fo
        from fiftyone import ViewField as F
    except Exception:  # noqa: BLE001
        return
    if DATASET not in fo.list_datasets():
        return
    ds = fo.load_dataset(DATASET)
    for h, (path, stage) in moves.items():
        for s in ds.match(F("content_hash") == h):
            s["filepath"] = path
            s["stage"] = stage
            s.save()


def is_promotable(img: dict) -> bool:
    """kept + brand/series/model 3종 완비면 training 승급 대상."""
    if img.get("review_state") != "kept":
        return False
    return not any(_blank(img.get(f)) for f in ("brand", "series", "model"))


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dst.resolve():
        return
    if dst.exists():
        src.unlink(missing_ok=True)
        return
    shutil.move(str(src), str(dst))


def run_sync() -> dict:
    """검수결과 반영 + 승급. 실패 시 트랜잭션 롤백."""
    samples = {s["content_hash"]: s for s in read_review_state()}
    kept = rejected = promoted = 0
    moves: dict[str, tuple[str, str]] = {}
    now = _now()

    with conn.session() as cx:
        cur = cx.execute("INSERT INTO sync_log (started_at) VALUES (?)", (now,))
        log_id = cur.lastrowid

        for row in cx.execute("SELECT * FROM image").fetchall():
            s = samples.get(row["content_hash"])
            if not s:
                continue

            # 1) 라벨 반영 (사람이 고친 값이 우선)
            labels = {}
            for f in LABEL_FIELDS:
                v = s.get(f)
                if not _blank(v):
                    labels[f] = normalize_brand(v) if f == "brand" else str(v).strip()

            # 2) 판정 반영
            tags = set(s.get("tags") or [])
            state = row["review_state"]
            if "reject" in tags:
                state = "rejected"
            elif "keep" in tags:
                state = "kept"

            merged = {**dict(row), **labels, "review_state": state}
            sets = {**labels, "review_state": state}

            if state == "rejected":
                rejected += 1
                sets["stage"] = "rejected"
                src = storage.DATA_ROOT / row["rel_path"]
                dst = storage.DATA_ROOT / "rejected" / f"{row['content_hash']}.{row['ext']}"
                if src.exists():
                    _move(src, dst)
                sets["rel_path"] = storage.rel(dst)
                moves[row["content_hash"]] = (str(dst.resolve()), "rejected")
            elif state == "kept":
                kept += 1
                if row["stage"] != "training" and is_promotable(merged):
                    dst = storage.stage_image_path(
                        "training", merged["brand"], merged["series"],
                        merged["model"], merged["modality"] or "catalog",
                        row["content_hash"], row["ext"])
                    src = storage.DATA_ROOT / row["rel_path"]
                    if src.exists():
                        _move(src, dst)
                    sets["stage"] = "training"
                    sets["rel_path"] = storage.rel(dst)
                    moves[row["content_hash"]] = (str(dst.resolve()), "training")
                    promoted += 1

            sets["reviewed_at"] = now
            cols = ", ".join(f"{k}=?" for k in sets)
            cx.execute(f"UPDATE image SET {cols} WHERE content_hash=?",
                       (*sets.values(), row["content_hash"]))

        note = f"샘플 {len(samples)}건 확인"
        cx.execute("""UPDATE sync_log SET finished_at=?, kept=?, rejected=?, promoted=?, note=?
                      WHERE id=?""", (_now(), kept, rejected, promoted, note, log_id))

    push_stage_to_fiftyone(moves)
    return {"kept": kept, "rejected": rejected, "promoted": promoted, "note": note}
