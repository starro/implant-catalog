"""FiftyOne 검수결과 → SQLite 반영 (수동 실행).

검수자는 FiftyOne 에서 두 가지를 한다.
  1) 태그로 판정: keep / reject
  2) 라벨 직접 수정: brand / series / surface / model

`run_sync()` 는 세 단계로 나뉜다. 각 단계는 서로 다른 실패 모드를 갖고,
뒤 단계의 실패가 앞 단계를 오염시키지 않도록 분리했다.

  1단계 (트랜잭션 안): DB 만 갱신 — 판정/라벨 반영, 승급 판단, 목표 rel_path 계산.
                      파일은 건드리지 않는다. 실패하면 DB 만 깨끗이 롤백된다.
  2단계 (커밋 후, 멱등): 파일 위치 보정 — DB 의 rel_path 위치에 파일이 없으면
                      1단계가 기억해 둔 이전 위치에서 옮긴다. 여러 번 돌려도 안전하다.
  3단계 (커밋 후, 멱등·재시도 가능): FiftyOne 반영 — "이번에 옮긴 것"이 아니라
                      "DB 와 FiftyOne 샘플이 어긋난 것 전부"를 갱신 대상으로 삼는다.
                      그래서 이전 동기화에서 실패한 샘플도 다음 동기화 때 자동 재시도된다.

버림은 삭제가 아니라 data/rejected/ 로 이동한다. 버림 후 FiftyOne 에서 keep 으로
오판을 되돌렸는데 라벨이 아직 불완전하면 review 로 되돌아간다(§B, 영구 rejected 방지).
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
    """FiftyOne 데이터셋에서 태그·라벨·현재 filepath/stage 를 읽어온다.

    filepath/stage 는 3단계에서 "DB 와 어긋난 것"을 판정하는 기준이 된다.
    미설치/데이터셋 없으면 빈 리스트.

    방어적 스키마 처리: 옛날에 등록된(예: surface 필드 추가 이전) 데이터셋에는 여기서 원하는
    필드가 일부 없을 수 있다. get_field_schema() 로 실제 존재하는 필드만 select_fields 에 넘기고,
    없는 필드는 None 으로 채운다 — 스키마에 없는 필드를 select_fields 로 요청하면 FiftyOne 이
    예외를 던지기 때문에, 이 방어가 없으면 옛 데이터셋을 만나는 즉시 "검수결과 반영"이 깨진다.
    """
    try:
        import fiftyone as fo
    except Exception:  # noqa: BLE001
        return []
    if DATASET not in fo.list_datasets():
        return []
    ds = fo.load_dataset(DATASET)
    schema = ds.get_field_schema()
    wanted = ["content_hash", "filepath", "stage", *LABEL_FIELDS]
    present = [f for f in wanted if f in schema]
    out = []
    for s in ds.select_fields(present):
        out.append({
            "content_hash": s["content_hash"] if "content_hash" in present else None,
            "tags": list(s.tags or []),
            "filepath": s["filepath"] if "filepath" in present else None,
            "stage": s["stage"] if "stage" in present else None,
            **{f: (s[f] if f in present else None) for f in LABEL_FIELDS},
        })
    return out


def push_stage_to_fiftyone(moves: dict[str, tuple[str, str]]) -> int:
    """샘플의 filepath 와 stage 를 DB 값으로 갱신 (증분, 재빌드 아님).

    개별 샘플 갱신 실패는 예외를 밖으로 던지지 않고 집계해서 반환한다.
    다음 `run_sync()` 호출 때 `_compute_fiftyone_moves()` 가 이 실패 건을 다시 대상으로 잡는다.
    """
    if not moves:
        return 0
    try:
        import fiftyone as fo
        from fiftyone import ViewField as F
    except Exception:  # noqa: BLE001
        return 0
    if DATASET not in fo.list_datasets():
        return 0
    ds = fo.load_dataset(DATASET)
    failed = 0
    for h, (path, stage) in moves.items():
        try:
            matched = False
            for s in ds.match(F("content_hash") == h):
                s["filepath"] = path
                s["stage"] = stage
                s.save()
                matched = True
            if not matched:
                failed += 1
        except Exception:  # noqa: BLE001
            failed += 1
    return failed


def delete_fiftyone_samples(hashes: list[str]) -> int:
    """버림 처리된 content_hash 샘플을 FiftyOne 데이터셋에서 제거.

    화면(라벨링 뷰)에서 버림 이미지가 실제로 사라지게 한다. 파일은 data/rejected/ 에,
    DB 행은 stage='rejected' 로 남아 있어 감사·복구는 가능하다(FiftyOne 재태깅으로는 복구 불가).
    실제 삭제한 수를 반환. 미설치/데이터셋 없음/오류 시 0.
    """
    if not hashes:
        return 0
    try:
        import fiftyone as fo
        from fiftyone import ViewField as F
    except Exception:  # noqa: BLE001
        return 0
    if DATASET not in fo.list_datasets():
        return 0
    ds = fo.load_dataset(DATASET)
    view = ds.match(F("content_hash").is_in(hashes))
    n = len(view)
    ds.delete_samples(view)
    return n


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


def _reconcile_files(prev_rel_path: dict[str, str]) -> int:
    """DB 의 rel_path 위치로 파일을 맞춘다 (2단계). 여러 번 돌려도 안전(멱등).

    prev_rel_path 에 없는데 목적지에도 파일이 없으면 추측하지 않고 실패로 집계한다.
    목적지에 이미 파일이 있으면(이전 실행이 부분적으로 성공한 경우) 원본만 정리하고 성공으로 친다.
    """
    with conn.session() as cx:
        rows = cx.execute("SELECT content_hash, rel_path FROM image").fetchall()

    failed = 0
    for row in rows:
        dst = storage.DATA_ROOT / row["rel_path"]
        src_rel = prev_rel_path.get(row["content_hash"])
        src = storage.DATA_ROOT / src_rel if src_rel else None

        if dst.exists():
            if src is not None and src.exists() and src.resolve() != dst.resolve():
                src.unlink(missing_ok=True)  # 같은 content_hash = 같은 내용 → 원본 정리
            continue

        if src is None or not src.exists():
            failed += 1  # 기억해 둔 이전 위치가 없거나 거기에도 없음 — 뒤지지 않는다
            continue

        try:
            _move(src, dst)
        except Exception:  # noqa: BLE001
            failed += 1
    return failed


def _compute_fiftyone_moves(samples: dict[str, dict]) -> dict[str, tuple[str, str]]:
    """DB 최종 상태와 FiftyOne 샘플이 어긋난 것 전부를 3단계 반영 대상으로 계산한다.

    "이번에 옮긴 것"이 아니라 전체를 비교하므로, 이전 동기화에서 실패해 filepath 가
    여전히 옛 경로를 가리키는 샘플도 자동으로 다시 잡힌다(재시도).
    """
    moves: dict[str, tuple[str, str]] = {}
    with conn.session() as cx:
        rows = cx.execute("SELECT content_hash, rel_path, stage FROM image").fetchall()
    for row in rows:
        s = samples.get(row["content_hash"])
        if not s:
            continue
        abs_path = str((storage.DATA_ROOT / row["rel_path"]).resolve())
        if s.get("filepath") != abs_path or s.get("stage") != row["stage"]:
            moves[row["content_hash"]] = (abs_path, row["stage"])
    return moves


def run_sync() -> dict:
    """검수결과 반영 + 승급. DB/파일이동/FiftyOne반영 3단계. 예외 대신 결과로 실패를 보고한다."""
    samples = {s["content_hash"]: s for s in read_review_state()}
    kept = rejected = promoted = 0
    prev_rel_path: dict[str, str] = {}
    now = _now()

    # ---- 1단계: DB 만 갱신 (트랜잭션, 파일 건드리지 않음) ----
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
            modality = merged.get("modality") or "catalog"

            if state == "rejected":
                rejected += 1
                sets["stage"] = "rejected"
                sets["rel_path"] = f"rejected/{row['content_hash']}.{row['ext']}"
            elif state == "kept":
                kept += 1
                if row["stage"] == "training":
                    pass  # 이미 승급됨 — 유지 (강등 없음)
                elif is_promotable(merged):
                    dst = storage.stage_image_path(
                        "training", merged["brand"], merged["series"],
                        merged["model"], modality, row["content_hash"], row["ext"])
                    sets["stage"] = "training"
                    sets["rel_path"] = storage.rel(dst)
                    promoted += 1
                elif row["stage"] == "rejected":
                    # B: 오판 복구 — 버림 → keep 이지만 라벨이 아직 불완전 → review 로 되돌림
                    dst = storage.stage_image_path(
                        "review", merged["brand"], merged["series"],
                        merged["model"], modality, row["content_hash"], row["ext"])
                    sets["stage"] = "review"
                    sets["rel_path"] = storage.rel(dst)

            if "rel_path" in sets and sets["rel_path"] != row["rel_path"]:
                prev_rel_path[row["content_hash"]] = row["rel_path"]

            sets["reviewed_at"] = now
            cols = ", ".join(f"{k}=?" for k in sets)
            cx.execute(f"UPDATE image SET {cols} WHERE content_hash=?",
                       (*sets.values(), row["content_hash"]))

        note = f"샘플 {len(samples)}건 확인"
        cx.execute("""UPDATE sync_log SET finished_at=?, kept=?, rejected=?, promoted=?, note=?
                      WHERE id=?""", (_now(), kept, rejected, promoted, note, log_id))

    # ---- 2단계: 파일 위치 보정 (커밋 후, 멱등) ----
    move_failed = _reconcile_files(prev_rel_path)

    # ---- 3단계: FiftyOne 반영 (커밋 후, 멱등·재시도 가능) ----
    # 버림된 것은 갱신이 아니라 FiftyOne 에서 제거해 라벨링 뷰에서 사라지게 한다.
    with conn.session() as cx:
        reject_set = {r["content_hash"] for r in cx.execute(
            "SELECT content_hash FROM image WHERE stage='rejected'").fetchall()}

    moves = _compute_fiftyone_moves(samples)
    moves = {h: v for h, v in moves.items() if h not in reject_set}   # 버림은 갱신 대상 제외
    fiftyone_failed = push_stage_to_fiftyone(moves) or 0
    # 아직 FiftyOne 에 남아 있는 버림 샘플만 삭제 (samples = 이번 읽기 시점에 존재하던 것)
    fiftyone_deleted = delete_fiftyone_samples([h for h in reject_set if h in samples])

    if move_failed or fiftyone_failed:
        note = f"{note}, 파일이동 실패 {move_failed}건, FiftyOne반영 실패 {fiftyone_failed}건"
        with conn.session() as cx:
            cx.execute("UPDATE sync_log SET note=? WHERE id=?", (note, log_id))

    # ---- saved view 자동 갱신 (실패해도 검수결과 반영 자체는 성공으로 취급) ----
    from scripts.fiftyone_saved_views import sync_views_safely
    saved_views = sync_views_safely()

    return {"kept": kept, "rejected": rejected, "promoted": promoted, "note": note,
            "move_failed": move_failed, "fiftyone_failed": fiftyone_failed,
            "fiftyone_deleted": fiftyone_deleted, "saved_views": saved_views}
