# 관리 UI 이식 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 관리 UI(Svelte SPA + Starlette API + SQLite)를 새 DGX 라벨링 엔진의 컨트롤 플레인으로 재배선한다 — Dagster를 경량 async 실행기로 대체하고, 무중단 docker exec+cp+즉시정리로 컨테이너 엔진을 돌리며, 단계별 현황을 한국어로 보여준다.

**Architecture:** 관리 API(호스트 Starlette)가 "실행" 요청을 받으면 SQLite에 run을 만들고 `runner_exec`가 `docker exec vllm-shlee label_catalog`로 컨테이너 엔진을 async 실행 → `docker cp`로 크롭을 호스트 영구저장소에 병합 → 컨테이너 tmp `rm -rf`(즉시) → manifest를 읽어 FiftyOne 등록 + SQLite 기록 + run 종료 + SSE. Dagster 스택은 제거하고 pyproject를 python 3.12 호환으로 연다.

**Tech Stack:** Python 3.12, Starlette, uvicorn, httpx, SQLite, Svelte 5 (vite/vitest), FiftyOne, (컨테이너) 새 라벨링 엔진.

## Global Constraints

- 작업 디렉토리 `c:/dev/Dr.HERi/data-pipeline`, 브랜치 `feature/pipeline-ui-redesign`. 테스트 = `.venv/Scripts/python.exe -m pytest`(파이썬), `cd web && npm test`(SPA).
- **무중단**: 컨테이너 재생성 금지. 트리거는 `docker exec`, 크롭 이동은 `docker cp`.
- **고아 데이터 0**: 런별 tmp `/engine/run_<id>`는 cp 직후 성공/실패 무관 `finally`에서 `rm -rf`.
- **동시성 1런**: GPU 공유라 전역 락으로 한 번에 하나만.
- **엔진 호출**: `docker exec <container> python -m drheri_pipeline.labeling.cli --pdf <..> --brand <..> [--pages ..] [--dpi ..] [--conf-min ..]`, 컨테이너 env `PYTHONPATH=/engine DATA_ROOT=/engine/run_<id>`. 컨테이너명 기본 `vllm-shlee`(env `ENGINE_CONTAINER`).
- **호스트 영구 저장**: `DATA_ROOT=/home/sh_lee/drheri-data`. content_hash 병합·중복제거.
- **용어 한국어**: 화면에서 "퍼널"→"단계별 현황", 단계=검출/검수대기/학습/버림.
- **Dagster 제거**: assets/definitions/sensors/config/dagster_client + 관련 테스트 삭제, pyproject에서 dagster 의존성·`[tool.dagster]` 제거, `requires-python`을 `>=3.11`(상한 제거)로.
- 기존 재사용: `db/`(conn/writes/queries/schema), `ui/app.py`, `ui/api/{sources,uploads,ops}.py`, `ui/events.py`(SSE), `labeling/fiftyone_writer.register_prelabeled`, `storage`, `review.py`.

---

## File Structure

```
drheri_pipeline/
  db/schema.sql            # 수정: image 에 is_fixture/diameter/diameter_src/needs_review 컬럼
  db/conn.py               # 수정: migrate() 가 없는 컬럼 idempotent ALTER
  db/writes.py             # 수정: record_image 가 새 필드 기록
  db/queries.py            # 수정: 단계별 현황에 needs_review/픽스처의심 집계
  ui/runner_exec.py        # 신규: 경량 실행기(docker exec/cp/rm + 등록 + 종료 + SSE)
  ui/api/runs.py           # 수정: collect 가 runner_exec 사용(Dagster 제거), 훅/reconcile 정리
  assets.py definitions.py sensors.py config.py ui/dagster_client.py   # 삭제
web/src/
  components/FunnelBar.svelte  # 수정: 라벨 한국어(검출/검수대기/학습/버림)
  routes/*.svelte, lib/*.js    # 수정: "퍼널"→"단계별 현황" 표기
pyproject.toml             # 수정: dagster 제거, requires-python 상한 제거
docs/DGX_UI_DEPLOY.md       # 신규: 호스트 배치 절차(systemd drheri-ui, docker 그룹)
tests/                     # test_runner_exec.py(신규), test_dagster_* 삭제, 기존 db/api 테스트 확장
```

---

## Task 1: DB — image 새 컬럼 + 멱등 마이그레이션

새 엔진 신호(is_fixture/diameter/diameter_src/needs_review)를 저장할 컬럼을 추가한다. 신규 DB는
schema.sql 로, 기존 DB는 `migrate()` 의 idempotent ALTER 로 채운다.

**Files:**
- Modify: `drheri_pipeline/db/schema.sql`(image 테이블), `drheri_pipeline/db/conn.py`(migrate)
- Test: `tests/test_conn.py`(기존 파일에 추가)

**Interfaces:**
- Produces: image 테이블에 `is_fixture INTEGER`, `diameter TEXT`, `diameter_src TEXT`, `needs_review INTEGER NOT NULL DEFAULT 0` 존재. `conn.migrate()` 는 여러 번 호출해도 안전.

- [ ] **Step 1: Write the failing test**

`tests/test_conn.py` 에 추가:
```python
def test_migrate_adds_new_image_columns(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    conn.migrate()
    conn.migrate()   # 멱등 — 두 번 호출해도 예외 없음
    cx = conn.connect()
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(image)").fetchall()}
    cx.close()
    assert {"is_fixture", "diameter", "diameter_src", "needs_review"} <= cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_conn.py::test_migrate_adds_new_image_columns -v`
Expected: FAIL — 컬럼 없음(KeyError/assert)

- [ ] **Step 3: Add columns to schema.sql (fresh DB)**

`db/schema.sql` 의 image 테이블 CREATE 에 컬럼 추가(기존 컬럼 뒤, `created_at` 앞 아무 곳):
```sql
  is_fixture   INTEGER,
  diameter     TEXT,
  diameter_src TEXT,
  needs_review INTEGER NOT NULL DEFAULT 0,
```

- [ ] **Step 4: Add idempotent ALTER in conn.migrate() (existing DB)**

`db/conn.py` 의 `migrate()` 를 다음으로 교체:
```python
_NEW_IMAGE_COLS = {
    "is_fixture": "INTEGER",
    "diameter": "TEXT",
    "diameter_src": "TEXT",
    "needs_review": "INTEGER NOT NULL DEFAULT 0",
}


def migrate() -> None:
    """schema.sql(멱등 CREATE) 실행 후, 기존 image 테이블에 없는 새 컬럼을 ALTER 로 채운다."""
    cx = connect()
    try:
        cx.executescript(SCHEMA.read_text(encoding="utf-8"))
        have = {r["name"] for r in cx.execute("PRAGMA table_info(image)").fetchall()}
        for col, decl in _NEW_IMAGE_COLS.items():
            if col not in have:
                cx.execute(f"ALTER TABLE image ADD COLUMN {col} {decl}")
    finally:
        cx.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_conn.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add drheri_pipeline/db/schema.sql drheri_pipeline/db/conn.py tests/test_conn.py
git commit -m "feat(db): image 에 is_fixture/diameter/diameter_src/needs_review + 멱등 마이그레이션"
```

---

## Task 2: db/writes — record_image 가 새 필드 기록

`record_image` 가 manifest 레코드의 새 필드를 image 행에 저장한다. 기존 행 라벨은 덮어쓰지 않는
정책(ON CONFLICT DO NOTHING) 유지.

**Files:**
- Modify: `drheri_pipeline/db/writes.py:88-104` (`record_image`)
- Test: `tests/test_writes.py`(기존 파일에 추가)

**Interfaces:**
- Consumes: manifest 레코드 dict — `is_fixture(bool|None)`, `diameter(str|None)`, `diameter_src(str|None)`, `needs_review(bool)` 키를 읽음(runner 가 생성).
- Produces: `record_image(cx, rec, document_id, run_id)` 가 image 행에 위 필드를 채움.

- [ ] **Step 1: Write the failing test**

`tests/test_writes.py` 에 추가:
```python
def test_record_image_stores_new_fields(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn, writes
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    conn.migrate()
    rec = {"content_hash": "h1", "path": "review/BEGO/catalog/h1.png", "brand": "BEGO",
           "model": "SC", "modality": "catalog", "page_no": 18, "bbox": [1, 2, 3, 4],
           "is_fixture": True, "diameter": "4.1", "diameter_src": "geom", "needs_review": False}
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u1",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        writes.record_image(cx, rec, d, None)
    cx = conn.connect()
    row = cx.execute("SELECT is_fixture, diameter, diameter_src, needs_review "
                     "FROM image WHERE content_hash='h1'").fetchone()
    cx.close()
    assert row["diameter"] == "4.1" and row["diameter_src"] == "geom"
    assert row["is_fixture"] == 1 and row["needs_review"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_writes.py::test_record_image_stores_new_fields -v`
Expected: FAIL — 컬럼에 값이 안 들어감(None)

- [ ] **Step 3: Update record_image**

`writes.py` 의 image INSERT 를 새 컬럼 포함으로 교체:
```python
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, surface, model, modality,
                              review_state, stage, rel_path, created_at,
                              is_fixture, diameter, diameter_src, needs_review)
           VALUES (?,?,?,?,?,?,?, 'pending', 'review', ?, ?, ?,?,?,?)
           ON CONFLICT(content_hash) DO NOTHING""",
        (h, ext, rec.get("brand"), rec.get("series"), rec.get("surface"),
         rec.get("model"), rec.get("modality"), rec.get("path"), now,
         1 if rec.get("is_fixture") else (0 if rec.get("is_fixture") is False else None),
         rec.get("diameter"), rec.get("diameter_src"),
         1 if rec.get("needs_review") else 0),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_writes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/db/writes.py tests/test_writes.py
git commit -m "feat(db): record_image 가 is_fixture/diameter/diameter_src/needs_review 기록"
```

---

## Task 3: db/queries — 단계별 현황에 검수대기/픽스처의심 집계

단계별 현황(구 funnel)에 `needs_review`(검수대기)와 `not_fixture`(픽스처의심=is_fixture=0) 카운트를
추가한다. 기존 키(extracted/training/rejected/pending/unreviewed/label_incomplete)는 유지(SPA 호환).

**Files:**
- Modify: `drheri_pipeline/db/queries.py:13-39` (`_FUNNEL_SELECT`, `EMPTY_FUNNEL`, `_funnel`)
- Test: `tests/test_queries.py`(기존 파일에 추가)

**Interfaces:**
- Produces: `funnel_for_document`/`overview` 반환 dict 에 `needs_review:int`, `not_fixture:int` 키 추가.

- [ ] **Step 1: Write the failing test**

`tests/test_queries.py` 에 추가:
```python
def test_funnel_counts_needs_review_and_not_fixture(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn, writes, queries
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    conn.migrate()
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u1",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        for h, nf, nr in [("a", True, True), ("b", False, True), ("c", True, False)]:
            writes.record_image(cx, {"content_hash": h, "path": f"{h}.png", "brand": "BEGO",
                                     "is_fixture": nf, "needs_review": nr}, d, None)
        f = queries.funnel_for_document(cx, d)
    assert f["extracted"] == 3 and f["needs_review"] == 2 and f["not_fixture"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_queries.py::test_funnel_counts_needs_review_and_not_fixture -v`
Expected: FAIL — KeyError 'needs_review'

- [ ] **Step 3: Update the funnel aggregation**

`queries.py`:
```python
_FUNNEL_SELECT = """
  COUNT(*)                                                     AS extracted,
  SUM(CASE WHEN i.stage='training'        THEN 1 ELSE 0 END)   AS training,
  SUM(CASE WHEN i.review_state='rejected' THEN 1 ELSE 0 END)   AS rejected,
  SUM(CASE WHEN i.review_state='pending'  THEN 1 ELSE 0 END)   AS unreviewed,
  SUM(CASE WHEN i.review_state='kept' AND i.stage<>'training'
                                          THEN 1 ELSE 0 END)   AS label_incomplete,
  SUM(CASE WHEN i.needs_review=1          THEN 1 ELSE 0 END)   AS needs_review,
  SUM(CASE WHEN i.is_fixture=0            THEN 1 ELSE 0 END)   AS not_fixture
"""

EMPTY_FUNNEL = {"extracted": 0, "training": 0, "rejected": 0, "pending": 0,
                "unreviewed": 0, "label_incomplete": 0, "needs_review": 0, "not_fixture": 0}
```
그리고 `_funnel()` 반환 dict 에 두 키 추가:
```python
    return {
        "extracted": extracted,
        "training": training,
        "rejected": rejected,
        "pending": extracted - training - rejected,
        "unreviewed": row["unreviewed"] or 0,
        "label_incomplete": row["label_incomplete"] or 0,
        "needs_review": row["needs_review"] or 0,
        "not_fixture": row["not_fixture"] or 0,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_queries.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/db/queries.py tests/test_queries.py
git commit -m "feat(db): 단계별 현황에 검수대기(needs_review)·픽스처의심(not_fixture) 집계"
```

---

## Task 4: runner_exec — 커맨드 빌더(순수 함수)

docker exec/cp/rm 커맨드를 순수 함수로 만들어 docker 없이 테스트 가능하게 한다.

**Files:**
- Create: `drheri_pipeline/ui/runner_exec.py`
- Test: `tests/test_runner_exec.py`

**Interfaces:**
- Produces:
  - `CONTAINER` (env `ENGINE_CONTAINER`, 기본 `"vllm-shlee"`)
  - `exec_cmd(run_id:int, pdf:str, brand:str, pages:str, dpi:int, conf_min:float) -> list[str]`
  - `cp_cmd(run_id:int) -> list[str]` (컨테이너 tmp → 호스트 `storage.DATA_ROOT`)
  - `rm_cmd(run_id:int) -> list[str]`
  - `tmp_dir(run_id:int) -> str` = `/engine/run_{run_id}`

- [ ] **Step 1: Write the failing test**

`tests/test_runner_exec.py`:
```python
from drheri_pipeline.ui import runner_exec as R


def test_exec_cmd_shape():
    cmd = R.exec_cmd(7, "/engine/run_7/src.pdf", "BEGO", "12-26", 200, 0.6)
    assert cmd[:3] == ["docker", "exec", R.CONTAINER]
    assert "-m" in cmd and "drheri_pipeline.labeling.cli" in cmd
    assert "--pdf" in cmd and "/engine/run_7/src.pdf" in cmd
    assert "--brand" in cmd and "BEGO" in cmd
    assert "--pages" in cmd and "12-26" in cmd
    # DATA_ROOT 은 런별 tmp 로
    joined = " ".join(cmd)
    assert "/engine/run_7" in joined


def test_exec_cmd_omits_empty_pages():
    cmd = R.exec_cmd(7, "http://x/a.pdf", "BEGO", "", 200, 0.6)
    assert "--pages" not in cmd


def test_cp_and_rm_cmd(monkeypatch, tmp_path):
    from drheri_pipeline import storage
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    cp = R.cp_cmd(7)
    assert cp[:3] == ["docker", "cp"]
    assert f"{R.CONTAINER}:/engine/run_7/." in cp
    assert str(tmp_path) in " ".join(cp)
    rm = R.rm_cmd(7)
    assert rm[:3] == ["docker", "exec", R.CONTAINER] and "rm" in rm and "/engine/run_7" in " ".join(rm)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_runner_exec.py -v`
Expected: FAIL — `ModuleNotFoundError: ...ui.runner_exec`

- [ ] **Step 3: Implement the command builders**

`ui/runner_exec.py`:
```python
"""경량 실행기 — Dagster 대체. 컨테이너 엔진을 docker exec 로 돌리고 크롭을 호스트로 cp,
런 tmp 즉시 rm, FiftyOne 등록 + run 종료 + SSE. GPU 공유라 한 번에 1런(전역 락)."""
from __future__ import annotations

import asyncio
import os

from drheri_pipeline import storage

CONTAINER = os.getenv("ENGINE_CONTAINER", "vllm-shlee")
ENGINE_PYTHONPATH = "/engine"


def tmp_dir(run_id: int) -> str:
    return f"/engine/run_{run_id}"


def exec_cmd(run_id: int, pdf: str, brand: str, pages: str, dpi: int, conf_min: float) -> list[str]:
    inner = (f"PYTHONPATH={ENGINE_PYTHONPATH} DATA_ROOT={tmp_dir(run_id)} "
             f"python -m drheri_pipeline.labeling.cli "
             f"--pdf {pdf!r} --brand {brand!r} --dpi {int(dpi)} --conf-min {float(conf_min)}")
    if pages:
        inner += f" --pages {pages!r}"
    return ["docker", "exec", CONTAINER, "bash", "-lc", inner]


def cp_cmd(run_id: int) -> list[str]:
    return ["docker", "cp", f"{CONTAINER}:{tmp_dir(run_id)}/.", str(storage.DATA_ROOT)]


def rm_cmd(run_id: int) -> list[str]:
    return ["docker", "exec", CONTAINER, "rm", "-rf", tmp_dir(run_id)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_runner_exec.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/ui/runner_exec.py tests/test_runner_exec.py
git commit -m "feat(ui): runner_exec 커맨드 빌더(docker exec/cp/rm)"
```

---

## Task 5: runner_exec — 실행 오케스트레이션 (등록·종료·SSE·즉시정리)

엔진을 async 실행하고, 끝나면 cp → (finally)rm → manifest 읽어 SQLite 기록 + FiftyOne 등록 →
run 종료 + SSE. 전역 락으로 1런씩.

**Files:**
- Modify: `drheri_pipeline/ui/runner_exec.py`
- Test: `tests/test_runner_exec.py`(추가)

**Interfaces:**
- Consumes: `exec_cmd/cp_cmd/rm_cmd`(Task 4), `db.conn/writes`, `storage`, `labeling.fiftyone_writer.register_prelabeled`, `ui.events.broadcaster`.
- Produces: `async def run_engine(doc_id:int, run_id:int, pdf:str, brand:str, pages:str, dpi:int, conf_min:float) -> None` — 완주 시 run SUCCESS/FAILURE + SSE. 실패·성공 무관 tmp rm.
- `_read_manifest() -> list[dict]` = 호스트 `storage.MANIFEST` 의 이 런 레코드(간단화: 전체 manifest 재로드는 안 하고, cp 로 병합된 `DATA_ROOT/manifest.jsonl` 을 읽되 이 run_id 로 필터). 구현에선 엔진이 tmp manifest 를 쓰고 cp 로 호스트 manifest 에 append 되므로, cp 후 tmp manifest 를 직접 읽는다(아래 코드).

- [ ] **Step 1: Write the failing test** (subprocess/등록/DB 모킹 — 순수 오케스트레이션)

`tests/test_runner_exec.py` 에 추가:
```python
import asyncio, json
import pytest
from drheri_pipeline.ui import runner_exec as R


class _Proc:
    def __init__(self, rc): self.returncode = rc
    async def wait(self): return self.returncode
    async def communicate(self): return (b"", b"")


def _setup(tmp_path, monkeypatch, rc=0, recs=None):
    from drheri_pipeline import storage
    from drheri_pipeline.db import conn
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(storage, "MANIFEST", tmp_path / "manifest.jsonl")
    conn.migrate()
    async def fake_exec(*a, **k): return _Proc(rc)
    monkeypatch.setattr(R.asyncio, "create_subprocess_exec", fake_exec)
    calls = {"cp": 0, "rm": 0}
    def fake_run(cmd, **k):
        if cmd[:2] == ["docker", "cp"]:
            calls["cp"] += 1
            # cp 가 tmp manifest 를 호스트로 옮겨온 것처럼 준비
            (tmp_path / "manifest.jsonl").write_text(
                "\n".join(json.dumps(r) for r in (recs or [])), encoding="utf-8")
        if "rm" in cmd:
            calls["rm"] += 1
        class R2: returncode = 0
        return R2()
    monkeypatch.setattr(R.subprocess, "run", fake_run)
    reg = {"n": 0}
    monkeypatch.setattr(R, "register_prelabeled", lambda records, log=print: reg.__setitem__("n", len(records)) or len(records))
    events = []
    monkeypatch.setattr(R.broadcaster, "publish", lambda t, p: events.append((t, p)))
    return calls, reg, events


def test_run_engine_success(tmp_path, monkeypatch):
    from drheri_pipeline.db import conn, writes
    recs = [{"content_hash": "h1", "path": "review/BEGO/catalog/h1.png", "brand": "BEGO",
             "is_fixture": True, "diameter": "4.1", "diameter_src": "geom",
             "needs_review": False, "page_no": 1, "bbox": [1, 2, 3, 4]}]
    calls, reg, events = _setup(tmp_path, monkeypatch, rc=0, recs=recs)
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u1",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        run_id = writes.create_run(cx, d, 0.3, 200, "")
    asyncio.run(R.run_engine(d, run_id, "http://x/a.pdf", "BEGO", "", 200, 0.6))
    cx = conn.connect()
    st = cx.execute("SELECT status FROM run WHERE id=?", (run_id,)).fetchone()["status"]
    cx.close()
    assert st == "SUCCESS" and reg["n"] == 1 and calls["rm"] == 1
    assert any(t == "run.finished" for t, _ in events)


def test_run_engine_failure_still_cleans_up(tmp_path, monkeypatch):
    from drheri_pipeline.db import conn, writes
    calls, reg, events = _setup(tmp_path, monkeypatch, rc=1, recs=[])
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="u2",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
        run_id = writes.create_run(cx, d, 0.3, 200, "")
    asyncio.run(R.run_engine(d, run_id, "http://x/a.pdf", "BEGO", "", 200, 0.6))
    cx = conn.connect()
    st = cx.execute("SELECT status FROM run WHERE id=?", (run_id,)).fetchone()["status"]
    cx.close()
    assert st == "FAILURE" and calls["rm"] == 1     # 실패해도 tmp 정리
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_runner_exec.py -k run_engine -v`
Expected: FAIL — `AttributeError: run_engine`

- [ ] **Step 3: Implement the orchestration**

`ui/runner_exec.py` 상단 import 에 추가:
```python
import json
import subprocess

from drheri_pipeline.db import conn, writes
from drheri_pipeline.labeling.fiftyone_writer import register_prelabeled
from drheri_pipeline.ui.events import broadcaster

_run_lock = asyncio.Lock()
```
그리고 함수 추가:
```python
def _read_tmp_manifest() -> list[dict]:
    """cp 로 호스트 DATA_ROOT/manifest.jsonl 에 병합된 이번 런 레코드 로드."""
    mf = storage.MANIFEST
    if not mf.exists():
        return []
    with mf.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _record(records: list[dict], document_id: int, run_id: int) -> int:
    if not records:
        return 0
    with conn.session() as cx:
        for r in records:
            writes.record_image(cx, r, document_id, run_id)
        cx.execute("UPDATE run SET extracted=? WHERE id=?", (len(records), run_id))
    return len(records)


async def run_engine(doc_id: int, run_id: int, pdf: str, brand: str, pages: str,
                     dpi: int, conf_min: float, log=print) -> None:
    async with _run_lock:
        with conn.session() as cx:
            cx.execute("UPDATE run SET status='RUNNING' WHERE id=?", (run_id,))
        status, extracted, error = "SUCCESS", 0, None
        try:
            proc = await asyncio.create_subprocess_exec(*exec_cmd(run_id, pdf, brand, pages, dpi, conf_min))
            rc = await proc.wait()
            if rc != 0:
                raise RuntimeError(f"engine exit {rc}")
            subprocess.run(cp_cmd(run_id), check=True)
            records = _read_tmp_manifest()
            extracted = _record(records, doc_id, run_id)
            register_prelabeled(records, log=log)
        except Exception as e:  # noqa: BLE001
            status, error = "FAILURE", f"{e.__class__.__name__}: {e}"
        finally:
            subprocess.run(rm_cmd(run_id), check=False)   # 성공/실패 무관 즉시 정리
        with conn.session() as cx:
            writes.finish_run(cx, run_id, status, extracted, error)
        broadcaster.publish("run.finished", {
            "ui_run_id": run_id, "document_id": doc_id, "status": status,
            "extracted": extracted, "error": error})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_runner_exec.py -v`
Expected: PASS (성공/실패 둘 다, rm 항상 호출)

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/ui/runner_exec.py tests/test_runner_exec.py
git commit -m "feat(ui): runner_exec 오케스트레이션(엔진 async 실행·cp·즉시rm·등록·종료·SSE)"
```

---

## Task 6: collect 엔드포인트 재배선 (Dagster → runner_exec)

`collect` 가 Dagster 대신 `runner_exec.run_engine` 을 async task 로 띄운다. Dagster 훅/reconcile
경로는 제거하고, SSE `events` 엔드포인트는 유지. 업로드 파일이면 실행 전 컨테이너 tmp 에 주입.

**Files:**
- Modify: `drheri_pipeline/ui/api/runs.py`
- Test: `tests/test_api_runs.py`(기존 — Dagster 목 → runner_exec 목으로 교체)

**Interfaces:**
- Consumes: `runner_exec.run_engine`, `runner_exec.tmp_dir`, `db.queries.document_detail`, `db.writes.create_run`.
- Produces: `POST /api/sources/{doc_id}/collect` → run 생성 + `run_engine` async 시작 → `{ui_run_id}`. `GET /api/events`(SSE) 유지.

- [ ] **Step 1: Write the failing test**

`tests/test_api_runs.py` 를 다음 핵심 테스트로 교체(기존 Dagster 목 테스트 삭제):
```python
import asyncio
from starlette.testclient import TestClient


def test_collect_starts_engine(tmp_path, monkeypatch):
    from drheri_pipeline import storage
    monkeypatch.setattr(storage, "DATA_ROOT", tmp_path)
    from drheri_pipeline.db import conn, writes
    conn.migrate()
    with conn.session() as cx:
        d = writes.create_document(cx, brand_raw="BEGO", name="c", url="http://x/a.pdf",
                                   source_type="catalog_vlm", default_conf=0.3, default_dpi=200,
                                   default_pages="", default_series="_unknown", memo="")
    started = {}
    async def fake_run_engine(doc_id, run_id, pdf, brand, pages, dpi, conf_min, log=print):
        started.update(doc_id=doc_id, run_id=run_id, pdf=pdf, brand=brand)
    from drheri_pipeline.ui.api import runs
    monkeypatch.setattr(runs.runner_exec, "run_engine", fake_run_engine)
    from drheri_pipeline.ui.app import create_app
    client = TestClient(create_app())
    r = client.post(f"/api/sources/{d}/collect", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] and body["data"]["ui_run_id"]
    # async task 가 실제로 스케줄됐는지 — 짧게 이벤트루프 양보
    import time; time.sleep(0.05)
    assert started.get("brand") == "BEGO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_api_runs.py::test_collect_starts_engine -v`
Expected: FAIL — collect 이 아직 dagster_client 사용

- [ ] **Step 3: Rewire runs.py**

`runs.py` 를 다음으로 재작성(Dagster 관련 import·훅·reconcile 제거, SSE 유지):
```python
"""수집 실행(경량) · SSE. Dagster 대신 runner_exec 로 컨테이너 엔진을 async 실행한다."""
from __future__ import annotations

import asyncio

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.ui import runner_exec
from drheri_pipeline.ui.envelope import ApiError, ok, read_json
from drheri_pipeline.ui.events import broadcaster


async def collect(request: Request):
    doc_id = request.path_params["doc_id"]
    body = await read_json(request, require_dict=False)

    def _prepare():
        with conn.session() as cx:
            d = queries.document_detail(cx, doc_id)
            if d is None:
                return None
            conf = float(body.get("conf", d["default_conf"]))
            dpi = int(body.get("dpi", d["default_dpi"]))
            pages = body.get("pages", d["default_pages"]) or ""
            run_id = writes.create_run(cx, doc_id, conf, dpi, pages)
            return d, conf, dpi, pages, run_id

    prepared = await run_in_threadpool(_prepare)
    if prepared is None:
        raise ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    d, conf, dpi, pages, run_id = prepared

    # GPU 공유라 한 번에 1런 — run_engine 내부 전역 락이 큐잉한다. 여기선 즉시 반환.
    asyncio.create_task(runner_exec.run_engine(
        doc_id, run_id, d["url"], d["brand_raw"] or d["brand"], pages, dpi, conf))
    return ok({"ui_run_id": run_id})


async def latest_run(request: Request):
    def _get():
        with conn.session() as cx:
            row = cx.execute(
                "SELECT * FROM run WHERE document_id=? ORDER BY started_at DESC LIMIT 1",
                (request.path_params["doc_id"],)).fetchone()
            return dict(row) if row else None
    run = await run_in_threadpool(_get)
    if run is None:
        raise ApiError("not_found", "수집 이력이 없습니다", status=404)
    return ok(run)


async def events(request: Request):
    q = broadcaster.subscribe()
    return StreamingResponse(broadcaster.sse_stream(q), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


routes = [
    Route("/api/sources/{doc_id:int}/collect", collect, methods=["POST"]),
    Route("/api/sources/{doc_id:int}/runs/latest", latest_run, methods=["GET"]),
    Route("/api/events", events, methods=["GET"]),
]
```
(참고: 업로드 파일 소스는 `d["url"]` 가 호스트 경로다. runner_exec 가 URL/호스트경로를 구분해
호스트경로면 `docker cp <경로> <container>:<tmp>/src.pdf` 후 `--pdf <tmp>/src.pdf` 로 넘기도록
Task 5 `run_engine` 에 분기를 두는 것은 **후속 최소 확장** — 이번 태스크는 URL 경로만 배선하고,
업로드 주입은 별도 커밋으로. 계획 §7 참조.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest tests/test_api_runs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add drheri_pipeline/ui/api/runs.py tests/test_api_runs.py
git commit -m "feat(ui): collect 을 runner_exec 로 재배선(Dagster 트리거 제거)"
```

---

## Task 7: Dagster 제거 + pyproject python 3.12 개방

Dagster 스택과 옛 추출 경로를 삭제하고, pyproject 를 python 3.12(DGX 호스트)에서 설치되도록 연다.

**Files:**
- Delete: `drheri_pipeline/assets.py`, `drheri_pipeline/definitions.py`, `drheri_pipeline/sensors.py`, `drheri_pipeline/config.py`, `drheri_pipeline/ui/dagster_client.py`, `tests/test_sensors.py`, `tests/test_backfill.py`, `tests/test_ingest_recording.py`
- Modify: `pyproject.toml`
- (site_xray/catalog_pdf 옛 소스는 남겨도 무방하나 Dagster 자산이 사라지므로 잡 실행 경로는 없음 — 코드는 유지, import 는 끊김)

**Interfaces:**
- Produces: `import drheri_pipeline.ui.app` 가 dagster 없이 성공. 전체 스위트가 dagster 미설치에서 통과.

- [ ] **Step 1: Delete Dagster files and their tests**

```bash
cd data-pipeline
git rm drheri_pipeline/assets.py drheri_pipeline/definitions.py drheri_pipeline/sensors.py \
       drheri_pipeline/config.py drheri_pipeline/ui/dagster_client.py \
       tests/test_sensors.py tests/test_backfill.py tests/test_ingest_recording.py
```

- [ ] **Step 2: Update pyproject.toml**

`pyproject.toml`:
- `requires-python = ">=3.11,<3.12"` → `requires-python = ">=3.11"`
- dependencies 에서 `"dagster==1.13.9"`, `"dagster-webserver==1.13.9"` 삭제
- `[tool.dagster]` 블록 삭제
- (extract/dev extras 유지)

- [ ] **Step 3: Grep for stale Dagster imports**

Run: `cd data-pipeline && grep -rn "dagster\|assets\|definitions\|sensors\|config import\|dagster_client" drheri_pipeline tests | grep -iv "conf\b"`
기대: `drheri_pipeline` 코드/테스트에 dagster·삭제모듈 import 잔존 없음. 있으면 제거(예: `catalog_pdf.py`/`site_xray.py` 가 `config` 를 import 하면, 해당 소스는 옛 경로라 import 만 지연/제거).
구체: `sources/catalog_pdf.py`·`sources/site_xray.py` 의 `from ..config import ...`(있다면) 제거하고 `ingest(config,...)` 는 그대로 두되 호출부가 없으므로 방치(테스트 없음). `assets` 를 import 하던 곳 없음(확인).

- [ ] **Step 4: Run full suite**

Run: `cd data-pipeline && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (dagster 테스트 삭제됨, 나머지 통과). `python -c "import drheri_pipeline.ui.app"` 도 성공.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: Dagster 스택 제거 + pyproject python 3.12 개방"
```

---

## Task 8: SPA — 단계별 현황 한국어화

화면 표기의 "퍼널"을 "단계별 현황"으로, 단계 라벨을 검출/검수대기/학습/버림으로 바꾼다.

**Files:**
- Modify: `web/src/components/FunnelBar.svelte`, `web/src/routes/{Overview,Sources,SourceDetail}.svelte`
- Test: `web/src/lib/format.test.js`(라벨 매핑 함수가 있으면 거기) 또는 신규 `web/src/components/funnel_labels.test.js`

**Interfaces:**
- Produces: FunnelBar 가 `{extracted,training,rejected,pending,needs_review,not_fixture}` 를 한국어 라벨(검출/학습/버림/대기/검수대기/픽스처의심)로 표시.

- [ ] **Step 1: Write the failing test**

`web/src/components/funnel_labels.test.js`:
```javascript
import { expect, test } from 'vitest';
import { STAGE_LABELS } from './funnel_labels.js';

test('한국어 단계 라벨', () => {
  expect(STAGE_LABELS.extracted).toBe('검출');
  expect(STAGE_LABELS.needs_review).toBe('검수대기');
  expect(STAGE_LABELS.training).toBe('학습');
  expect(STAGE_LABELS.rejected).toBe('버림');
  expect(STAGE_LABELS.not_fixture).toBe('픽스처의심');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd data-pipeline/web && npm test`
Expected: FAIL — `funnel_labels.js` 없음

- [ ] **Step 3: Add label map + use it**

`web/src/components/funnel_labels.js`:
```javascript
export const STAGE_LABELS = {
  extracted: '검출',
  needs_review: '검수대기',
  training: '학습',
  rejected: '버림',
  pending: '대기',
  not_fixture: '픽스처의심',
};
```
그리고 `FunnelBar.svelte` 가 하드코딩 라벨 대신 `STAGE_LABELS` 를 import 해 사용하고, 제목/툴팁의
"퍼널" 문자열을 "단계별 현황" 으로 교체. `Overview/Sources/SourceDetail.svelte` 의 "퍼널" 표기도 동일 교체.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd data-pipeline/web && npm test`
Expected: PASS. 빌드 확인: `npm run build` 성공.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/funnel_labels.js web/src/components/FunnelBar.svelte web/src/components/funnel_labels.test.js web/src/routes
git commit -m "feat(web): 단계별 현황 한국어화(검출/검수대기/학습/버림/픽스처의심)"
```

---

## Task 9: DGX 호스트 배치 — systemd drheri-ui + docker 그룹

관리 API 를 DGX 호스트에 systemd 서비스로 올리고 IP 접속. sh_lee 를 docker 그룹에 넣어 exec sudo 제거.
산출물 = 배치 문서 + 스모크.

**Files:**
- Create: `docs/DGX_UI_DEPLOY.md`
- Depends on: Tasks 1–8

- [ ] **Step 1: 호스트 준비(무중단)**

```bash
# sh_lee 가 sudo 없이 docker 쓰게(그룹 반영 위해 재로그인/newgrp)
sudo usermod -aG docker sh_lee     # 컨테이너 재생성 아님 — 무중단
# 관리 API venv (fiftyone 있는 foenv 재사용 또는 별도)
/home/sh_lee/foenv/bin/pip install -q starlette uvicorn httpx python-multipart
# 엔진 코드 배포(기존과 동일 경로 /home/sh_lee/engine 에 drheri_pipeline 최신)
```
검증: `newgrp docker; docker ps` 가 sudo 없이 동작. `python -c "import starlette, uvicorn"`.

- [ ] **Step 2: SPA 빌드 → web/dist**

```bash
cd /home/sh_lee/engine/web && npm ci && npm run build   # web/dist 생성
```
(호스트에 node 필요 — 없으면 로컬 빌드 후 web/dist 를 pscp)
검증: `web/dist/index.html` 존재.

- [ ] **Step 3: systemd 서비스 기동**

```bash
sudo systemd-run --uid=sh_lee --gid=sh_lee \
  --setenv=HOME=/home/sh_lee \
  --setenv=DATA_ROOT=/home/sh_lee/drheri-data \
  --setenv=PYTHONPATH=/home/sh_lee/engine \
  --setenv=ENGINE_CONTAINER=vllm-shlee \
  --unit=drheri-ui \
  /home/sh_lee/foenv/bin/uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000
```
검증: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/` → 200(또는 SPA). `ss -tlnp | grep 3000` 0.0.0.0.

- [ ] **Step 4: BEGO end-to-end 스모크**

브라우저(LAN) `http://172.30.1.6:3000` → 소스 등록(BEGO, BEGO-2018.pdf URL 또는 업로드) → "수집 실행"(pages 18) → 진행 후 단계별 현황에 검출 5 반영 → "FiftyOne 에서 보기" 로 크롭 확인.
검증(호스트): `run` 상태 SUCCESS, `/home/sh_lee/drheri-data/review/BEGO/catalog/*.png` 5장, 컨테이너 `/engine/run_<id>` 삭제됨(`docker exec vllm-shlee ls /engine | grep run_ || echo clean`).

- [ ] **Step 5: 문서화 + 커밋**

`docs/DGX_UI_DEPLOY.md` 에 위 절차(docker 그룹·venv·빌드·systemd·스모크·재기동 `systemctl restart drheri-ui`) 정리.
```bash
git add docs/DGX_UI_DEPLOY.md
git commit -m "docs: DGX 관리 UI 호스트 배치 절차 + BEGO 스모크"
```

---

## Self-Review

**1. Spec coverage:**
- §3 오케스트레이션(Dagster 제거·경량) → Task 5·6·7. 위치(호스트 systemd) → Task 9. 실행트리거(무중단 docker exec) → Task 4·5. 크롭이동(cp+즉시rm) → Task 4·5(finally rm). 데이터(호스트 DATA_ROOT 병합) → Task 5. 용어(한국어) → Task 8.
- §4 실행흐름 → Task 5 `run_engine` 이 exec→cp→rm→등록→종료→SSE 전부.
- §5 재사용/신규 → 재사용(db/app/events/fiftyone_writer) 유지, 신규 runner_exec(4·5), 삭제 Dagster(7).
- §6 단계별 현황(검출/검수대기/학습/버림+is_fixture) → Task 3(집계)·8(라벨).
- §7 소스입력(URL/업로드) → Task 6(URL 배선). **업로드 파일 주입은 Task 6 Step 3 주석대로 후속 최소확장** — 갭으로 명시: 업로드 소스 실행은 이 계획 범위에서 "URL 경로만" 완결, 파일주입은 별도 커밋(계획에 태스크로 안 넣음 — YAGNI, 등록/URL 흐름 먼저).
- §8 에러/정리(고아0·1런큐·타임아웃) → Task 5(finally rm·전역락). **타임아웃 상한은 미구현** — 갭: run_engine 에 `asyncio.wait_for` 상한을 후속 추가(현재 무제한). 명시.
- §9 테스트 → 각 태스크 TDD. 통합 → Task 9 스모크.
- §10 배치 → Task 9. §11 승격지점 → 문서 유지.

**2. Placeholder scan:** "TODO/TBD" 없음. 업로드 주입·타임아웃 상한은 "후속/갭"으로 명시(플레이스홀더 아님, 범위 밖 결정).

**3. Type consistency:** `run_engine(doc_id,run_id,pdf,brand,pages,dpi,conf_min,log)` — Task 5 정의 ↔ Task 6 호출 일치. `exec_cmd/cp_cmd/rm_cmd(run_id,...)` — Task 4 정의 ↔ Task 5 사용 일치. 레코드 dict 키(is_fixture/diameter/diameter_src/needs_review/path/content_hash/bbox/page_no) — 엔진 생성 ↔ writes.record_image(Task 2) ↔ funnel(Task 3) 일치. STAGE_LABELS 키 ↔ funnel 키 일치.

**갭 요약(의도된 범위 밖, 후속 커밋):** (a) 업로드 파일 → 컨테이너 주입(현재 URL만), (b) run_engine 타임아웃 상한. 둘 다 코어 흐름과 독립이라 이번 플랜 후 최소 추가.
