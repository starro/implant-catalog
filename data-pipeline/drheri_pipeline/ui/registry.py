"""수집 소스 레지스트리 — `sources.jsonl` (URL 별 수집 이력 + 중복 체크).

append-only 로그. 같은 id 가 여러 번 쓰이면 최신 것만 채택(manifest 와 같은 방식).
"""
import json
import uuid
from datetime import datetime, timezone

from drheri_pipeline import storage

REGISTRY = storage.DATA_ROOT / "sources.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def read_all() -> list[dict]:
    if not REGISTRY.exists():
        return []
    with REGISTRY.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def latest_by_id() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in read_all():
        out[r["id"]] = r          # 뒤(최신)가 앞을 덮어씀
    return out


def history() -> list[dict]:
    """최신순 수집 이력."""
    return sorted(latest_by_id().values(), key=lambda r: r.get("created_at", ""), reverse=True)


def add(entry: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def update(entry_id: str, **fields) -> None:
    cur = latest_by_id().get(entry_id)
    if not cur:
        return
    add({**cur, **fields, "updated_at": now_iso()})


def find_by_url(url: str) -> list[dict]:
    """같은 URL 로 수집한 이력 (중복 체크용)."""
    u = (url or "").strip()
    return [r for r in history() if (r.get("url") or "").strip() == u]


def stage_counts() -> dict:
    """manifest 기준 단계별 현황 — 중간단계(review) / 학습용(training)."""
    latest = storage.latest_by_hash()
    review = sum(1 for r in latest.values() if r.get("stage") == "review")
    training = sum(1 for r in latest.values() if r.get("stage") == "training")
    labeled = sum(1 for r in latest.values()
                  if r.get("stage") == "review" and (r.get("series") or "_unknown") != "_unknown")
    return {"review": review, "training": training, "labeled_waiting": labeled}


def figures_for_url(url: str) -> int:
    """해당 URL 에서 수집된 figure 수 (manifest 의 origin_url 기준)."""
    u = (url or "").strip()
    return sum(1 for r in storage.latest_by_hash().values()
               if u and u in (r.get("origin_url") or ""))
