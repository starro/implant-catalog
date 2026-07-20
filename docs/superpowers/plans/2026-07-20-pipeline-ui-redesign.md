# Dr.HERi 파이프라인 관리 UI 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 소스(브랜드 › 문서) 중심 관리 UI 로 재설계하고, 운영 데이터를 SQLite 로 옮겨 소스별 퍼널(추출/학습/버림/대기)을 추적한다.

**Architecture:** SQLite(`data/pipeline.db`) 를 운영 DB 로 두고 Dagster 수집 잡과 Starlette UI 서버가 함께 쓴다. UI 서버는 `/api/*` JSON 만 제공하고 화면은 빌드된 Svelte 5 SPA 를 정적 서빙한다. 수집 완료는 Dagster `run_status_sensor` → UI 훅 → SSE 로 브라우저에 푸시한다. 이미지 보기·라벨링은 FiftyOne 이 담당하고, 검수 결과는 수동 sync 로 SQLite 에 반영한다.

**Tech Stack:** Python 3.11, Dagster 1.13.9, Starlette + uvicorn, SQLite(stdlib `sqlite3`), FiftyOne 1.17, Svelte 5 + Vite, pytest

**Spec:** `docs/superpowers/specs/2026-07-20-pipeline-ui-redesign-design.md`

## Global Constraints

- 작업 루트는 `c:\dev\Dr.HERi\data-pipeline` (배포는 개발서버 58.229.105.3 의 동일 레포). 아래 모든 경로는 이 디렉토리 기준 상대경로다.
- Python 은 `>=3.11,<3.12`. 가상환경은 `.venv`, 실행은 `.venv/bin/python` (Linux) / `.venv/Scripts/python` (Windows).
- 시간 값은 전부 UTC ISO8601 문자열(`datetime.now(timezone.utc).isoformat()`). `LocalDateTime` 류 로컬 시간 저장 금지.
- HTTP 메서드는 **GET/POST 만** 사용한다. PUT/DELETE/PATCH 금지.
- API 응답 봉투는 항상 `{"ok": bool, "data": ..., "error": {"code": str, "message": str} | null}`.
- `drheri_pipeline/assets.py` 에는 `from __future__ import annotations` 를 절대 추가하지 않는다 (Dagster Config 해석이 깨진다).
- FiftyOne 데이터셋 이름은 `drheri` 고정. 데이터셋 **전체 재빌드 금지** — 언제나 `content_hash` 기준 증분 추가.
- FiftyOne 관련 프로세스 실행 시 환경변수 `FIFTYONE_DATABASE_VALIDATION=false` 를 반드시 설정한다 (MongoDB 4.4 사용 중, 버전 검증에서 실패함).
- UI 포트는 3000, Dagster 3333, FiftyOne 5151, mongod 27017. 이 값들은 환경변수로 오버라이드 가능해야 한다.
- 라벨 정규화는 반드시 `drheri_pipeline/taxonomy.py` 의 `normalize_brand()` / `compose_series()` 를 쓴다. 새 정규화 로직을 따로 만들지 않는다.
- 커밋 메시지는 한글 본문, `feat:` / `fix:` / `refactor:` / `test:` / `docs:` 접두사.

---

## 사전 준비 (Task 0)

`c:\dev\Dr.HERi` 는 아직 git 저장소가 아니다. Task 1 을 시작하기 전에 한 번만 실행한다.

```bash
cd /c/dev/Dr.HERi
git init
printf '%s\n' 'data/' '.venv/' '__pycache__/' '*.pyc' 'node_modules/' 'dist/' '접속정보/' > .gitignore
git add .gitignore CLAUDE.md design docs md_files data-pipeline
git commit -m "chore: 저장소 초기화"
```

---

## File Structure

**신규 (Python)**
| 파일 | 책임 |
|---|---|
| `drheri_pipeline/db/__init__.py` | 공개 API 재노출 |
| `drheri_pipeline/db/schema.sql` | 테이블 DDL (단일 진실) |
| `drheri_pipeline/db/conn.py` | 커넥션·WAL·마이그레이션 실행 |
| `drheri_pipeline/db/writes.py` | 쓰기 — 브랜드/문서/런/이미지/출처/동기화로그 |
| `drheri_pipeline/db/queries.py` | 읽기 — 퍼널 집계, 트리, 상세, 현황 |
| `drheri_pipeline/services/fiftyone_ctl.py` | FiftyOne 정지·좀비정리·기동·헬스체크 |
| `drheri_pipeline/services/sync.py` | FiftyOne 검수결과 → SQLite 반영 + 승급 |
| `drheri_pipeline/services/export.py` | SQLite → labels.tsv / manifest.jsonl |
| `drheri_pipeline/ui/events.py` | SSE 브로드캐스터 |
| `drheri_pipeline/ui/api/sources.py` | 소스 CRUD 라우트 |
| `drheri_pipeline/ui/api/runs.py` | 수집 실행·상태·훅 라우트 |
| `drheri_pipeline/ui/api/ops.py` | sync/export/overview/settings/health/restart 라우트 |
| `drheri_pipeline/ui/envelope.py` | `{ok,data,error}` 봉투 + 예외 핸들러 |
| `drheri_pipeline/sensors.py` | Dagster `run_status_sensor` → UI 훅 POST |
| `scripts/backfill_db.py` | jsonl → SQLite 최초 백필 (멱등) |
| `tests/…` | pytest |

**신규 (프론트엔드)** — `web/` 아래. 상세는 Task 11 에서 정의.

**수정**
| 파일 | 변경 |
|---|---|
| `drheri_pipeline/assets.py` | manifest 대신 DB 기록, `run_id`/`document_id` 를 config 로 수신 |
| `drheri_pipeline/config.py` | `CatalogPdfConfig`/`SiteXrayConfig` 에 `document_id`, `ui_run_id` 추가 |
| `drheri_pipeline/definitions.py` | 센서 등록 |
| `drheri_pipeline/ui/app.py` | Jinja2 라우트 제거 → API 마운트 + 정적 서빙 |
| `drheri_pipeline/ui/dagster_client.py` | `submit()` 시그니처에 문서/런 식별자 추가 |
| `pyproject.toml` | pytest 추가 |

**삭제 (마지막 Task)**: `drheri_pipeline/ui/templates/index.html`, `drheri_pipeline/ui/registry.py`, `scripts/promote_reviewed.py`(+`.sh`)

---

### Task 1: SQLite 스키마 + 커넥션 모듈

**Files:**
- Create: `drheri_pipeline/db/__init__.py`
- Create: `drheri_pipeline/db/schema.sql`
- Create: `drheri_pipeline/db/conn.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_conn.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `drheri_pipeline.storage.DATA_ROOT`
- Produces:
  - `conn.db_path() -> pathlib.Path`
  - `conn.connect() -> sqlite3.Connection` (row_factory=`sqlite3.Row`, WAL, FK on)
  - `conn.migrate() -> None` (멱등, `schema.sql` 실행)
  - `conn.session()` — contextmanager, 커밋/롤백 자동

- [ ] **Step 1: pytest 의존성 추가**

`pyproject.toml` 의 `[project.optional-dependencies]` 블록을 다음으로 교체한다.

```toml
[project.optional-dependencies]
extract = ["doclayout-yolo>=0.0.4"]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/__init__.py` 는 빈 파일로 만든다.

`tests/conftest.py`:

```python
import os
import tempfile

import pytest


@pytest.fixture()
def data_root(monkeypatch):
    """테스트마다 격리된 DATA_ROOT — storage 모듈이 import 시점에 읽으므로 reload 한다."""
    import importlib

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("DATA_ROOT", tmp)
        import drheri_pipeline.storage as storage
        importlib.reload(storage)
        import drheri_pipeline.db.conn as conn
        importlib.reload(conn)
        conn.migrate()
        yield storage.DATA_ROOT
```

`tests/test_conn.py`:

```python
from drheri_pipeline.db import conn


def test_migrate_creates_all_tables(data_root):
    with conn.session() as cx:
        rows = cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r["name"] for r in rows}
    assert {"brand", "document", "run", "image", "image_origin", "sync_log"} <= names


def test_migrate_is_idempotent(data_root):
    conn.migrate()
    conn.migrate()
    with conn.session() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM brand").fetchone()["c"]
    assert n == 0


def test_wal_and_foreign_keys_enabled(data_root):
    with conn.session() as cx:
        assert cx.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert cx.execute("PRAGMA foreign_keys").fetchone()[0] == 1
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_conn.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drheri_pipeline.db'`

- [ ] **Step 4: 스키마 작성**

`drheri_pipeline/db/schema.sql`:

```sql
-- Dr.HERi 파이프라인 운영 DB. 모든 시각은 UTC ISO8601 문자열.
CREATE TABLE IF NOT EXISTS brand (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name_norm  TEXT NOT NULL UNIQUE,          -- taxonomy 정규화 결과 (OSSTEM IMPLANT)
  name_raw   TEXT NOT NULL,                 -- 사용자가 입력한 원문 (Osstem)
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document (       -- 소스 1건 = URL 1개
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  brand_id        INTEGER NOT NULL REFERENCES brand(id),
  name            TEXT NOT NULL,
  url             TEXT NOT NULL UNIQUE,
  source_type     TEXT NOT NULL,            -- catalog_pdf | site_xray
  default_conf    REAL NOT NULL DEFAULT 0.35,
  default_dpi     INTEGER NOT NULL DEFAULT 200,
  default_pages   TEXT NOT NULL DEFAULT '',
  default_series  TEXT NOT NULL DEFAULT '_unknown',
  memo            TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'active',   -- active | archived
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_document_brand ON document(brand_id);

CREATE TABLE IF NOT EXISTS run (            -- 수집 실행 1회
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id    INTEGER NOT NULL REFERENCES document(id),
  dagster_run_id TEXT,
  conf           REAL NOT NULL,
  dpi            INTEGER NOT NULL,
  pages          TEXT NOT NULL DEFAULT '',
  status         TEXT NOT NULL,             -- QUEUED|RUNNING|SUCCESS|FAILURE|TIMEOUT
  extracted      INTEGER NOT NULL DEFAULT 0,
  started_at     TEXT NOT NULL,
  finished_at    TEXT,
  error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_document ON run(document_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_dagster  ON run(dagster_run_id);

CREATE TABLE IF NOT EXISTS image (          -- 이미지 1장 = content_hash 1개
  content_hash TEXT PRIMARY KEY,
  ext          TEXT NOT NULL DEFAULT 'png',
  width        INTEGER,
  height       INTEGER,
  brand        TEXT,
  series       TEXT,
  surface      TEXT,
  model        TEXT,
  modality     TEXT,
  review_state TEXT NOT NULL DEFAULT 'pending',   -- pending | kept | rejected
  reject_reason TEXT,
  reviewed_at  TEXT,
  stage        TEXT NOT NULL DEFAULT 'review',    -- review | training | rejected
  rel_path     TEXT NOT NULL,
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_image_stage ON image(stage, review_state);

CREATE TABLE IF NOT EXISTS image_origin (   -- 출처 추적
  content_hash TEXT NOT NULL REFERENCES image(content_hash),
  document_id  INTEGER NOT NULL REFERENCES document(id),
  run_id       INTEGER REFERENCES run(id),
  page_no      INTEGER,
  bbox         TEXT,                         -- JSON 배열 문자열 "[x1,y1,x2,y2]"
  created_at   TEXT NOT NULL,
  PRIMARY KEY (content_hash, document_id)
);
CREATE INDEX IF NOT EXISTS idx_origin_document ON image_origin(document_id);

CREATE TABLE IF NOT EXISTS sync_log (       -- 검수 동기화 실행 기록
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  kept        INTEGER NOT NULL DEFAULT 0,
  rejected    INTEGER NOT NULL DEFAULT 0,
  promoted    INTEGER NOT NULL DEFAULT 0,
  note        TEXT
);
```

- [ ] **Step 5: 커넥션 모듈 구현**

`drheri_pipeline/db/conn.py`:

```python
"""SQLite 커넥션 — WAL 모드, 멱등 마이그레이션.

Dagster 수집 잡과 UI 서버 두 프로세스가 같은 파일을 쓴다. WAL + busy_timeout 으로
동시 접근을 견딘다(쓰기는 짧은 트랜잭션만).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from drheri_pipeline import storage

SCHEMA = Path(__file__).with_name("schema.sql")


def db_path() -> Path:
    p = storage.DATA_ROOT / "pipeline.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect() -> sqlite3.Connection:
    cx = sqlite3.connect(db_path(), timeout=30, isolation_level=None)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("PRAGMA foreign_keys=ON")
    cx.execute("PRAGMA busy_timeout=30000")
    return cx


def migrate() -> None:
    """schema.sql 을 그대로 실행. 전부 IF NOT EXISTS 라 멱등."""
    cx = connect()
    try:
        cx.executescript(SCHEMA.read_text(encoding="utf-8"))
    finally:
        cx.close()


@contextmanager
def session():
    """트랜잭션 세션 — 정상 종료 시 커밋, 예외 시 롤백."""
    cx = connect()
    try:
        cx.execute("BEGIN")
        yield cx
        cx.execute("COMMIT")
    except Exception:
        cx.execute("ROLLBACK")
        raise
    finally:
        cx.close()
```

`drheri_pipeline/db/__init__.py`:

```python
"""파이프라인 운영 DB (SQLite)."""
from .conn import connect, db_path, migrate, session

__all__ = ["connect", "db_path", "migrate", "session"]
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_conn.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: 커밋**

```bash
git add pyproject.toml drheri_pipeline/db tests
git commit -m "feat: SQLite 운영 DB 스키마와 커넥션 모듈 추가"
```

---

### Task 2: 쓰기 계층 (브랜드/문서/런/이미지)

**Files:**
- Create: `drheri_pipeline/db/writes.py`
- Test: `tests/test_writes.py`

**Interfaces:**
- Consumes: `db.conn.session`, `taxonomy.normalize_brand`
- Produces:
  - `writes.upsert_brand(cx, name_raw: str) -> int`
  - `writes.create_document(cx, brand_raw: str, name: str, url: str, source_type: str, default_conf: float, default_dpi: int, default_pages: str, default_series: str, memo: str) -> int`
  - `writes.update_document(cx, doc_id: int, **fields) -> None`
  - `writes.archive_document(cx, doc_id: int) -> None`
  - `writes.create_run(cx, document_id: int, conf: float, dpi: int, pages: str) -> int`
  - `writes.attach_dagster_run(cx, run_id: int, dagster_run_id: str) -> None`
  - `writes.finish_run(cx, run_id: int, status: str, extracted: int, error: str | None) -> None`
  - `writes.record_image(cx, rec: dict, document_id: int, run_id: int | None) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_writes.py`:

```python
import pytest

from drheri_pipeline.db import conn, writes


def _doc(cx, url="https://ex.com/a.pdf"):
    return writes.create_document(
        cx, brand_raw="Osstem", name="TS 카탈로그", url=url,
        source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
        default_pages="", default_series="_unknown", memo="",
    )


def test_upsert_brand_normalizes_and_dedupes(data_root):
    with conn.session() as cx:
        a = writes.upsert_brand(cx, "Osstem")
        b = writes.upsert_brand(cx, "osstem implant")
    assert a == b
    with conn.session() as cx:
        row = cx.execute("SELECT name_norm FROM brand WHERE id=?", (a,)).fetchone()
    assert row["name_norm"] == "OSSTEM IMPLANT"


def test_create_document_rejects_duplicate_url(data_root):
    with conn.session() as cx:
        _doc(cx)
    with pytest.raises(writes.DuplicateUrl):
        with conn.session() as cx:
            _doc(cx)


def test_run_lifecycle(data_root):
    with conn.session() as cx:
        doc = _doc(cx)
        run = writes.create_run(cx, doc, 0.35, 200, "1,2")
        writes.attach_dagster_run(cx, run, "abc123")
        writes.finish_run(cx, run, "SUCCESS", 7, None)
        row = cx.execute("SELECT * FROM run WHERE id=?", (run,)).fetchone()
    assert row["status"] == "SUCCESS"
    assert row["extracted"] == 7
    assert row["dagster_run_id"] == "abc123"
    assert row["finished_at"]


def test_record_image_is_idempotent_and_links_origin(data_root):
    rec = {
        "content_hash": "h1", "path": "review/x/h1.png", "brand": "Osstem",
        "series": "_unknown", "surface": None, "model": "_unknown",
        "modality": "catalog", "page_no": 3, "bbox": [1, 2, 3, 4],
    }
    with conn.session() as cx:
        doc = _doc(cx)
        run = writes.create_run(cx, doc, 0.35, 200, "")
        writes.record_image(cx, rec, doc, run)
        writes.record_image(cx, rec, doc, run)      # 재수집 — 부풀지 않아야 함
        imgs = cx.execute("SELECT COUNT(*) c FROM image").fetchone()["c"]
        orgs = cx.execute("SELECT COUNT(*) c FROM image_origin").fetchone()["c"]
    assert imgs == 1
    assert orgs == 1


def test_same_image_from_two_documents_has_two_origins(data_root):
    rec = {"content_hash": "h1", "path": "review/x/h1.png", "brand": "Osstem",
           "series": "_unknown", "surface": None, "model": "_unknown",
           "modality": "catalog", "page_no": 1, "bbox": [0, 0, 1, 1]}
    with conn.session() as cx:
        d1 = _doc(cx, "https://ex.com/a.pdf")
        d2 = _doc(cx, "https://ex.com/b.pdf")
        writes.record_image(cx, rec, d1, None)
        writes.record_image(cx, rec, d2, None)
        imgs = cx.execute("SELECT COUNT(*) c FROM image").fetchone()["c"]
        orgs = cx.execute("SELECT COUNT(*) c FROM image_origin").fetchone()["c"]
    assert imgs == 1
    assert orgs == 2
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_writes.py -v`
Expected: FAIL — `ImportError: cannot import name 'writes'`

- [ ] **Step 3: 구현**

`drheri_pipeline/db/writes.py`:

```python
"""운영 DB 쓰기 — 모든 함수는 커넥션(cx)을 인자로 받아 호출자 트랜잭션에 참여한다."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from drheri_pipeline.taxonomy import normalize_brand


class DuplicateUrl(Exception):
    """이미 등록된 URL."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_brand(cx: sqlite3.Connection, name_raw: str) -> int:
    norm = normalize_brand(name_raw) or "_unknown"
    row = cx.execute("SELECT id FROM brand WHERE name_norm=?", (norm,)).fetchone()
    if row:
        return row["id"]
    cur = cx.execute(
        "INSERT INTO brand (name_norm, name_raw, created_at) VALUES (?,?,?)",
        (norm, (name_raw or "").strip(), _now()),
    )
    return cur.lastrowid


def create_document(cx: sqlite3.Connection, *, brand_raw: str, name: str, url: str,
                    source_type: str, default_conf: float, default_dpi: int,
                    default_pages: str, default_series: str, memo: str) -> int:
    brand_id = upsert_brand(cx, brand_raw)
    now = _now()
    try:
        cur = cx.execute(
            """INSERT INTO document
               (brand_id, name, url, source_type, default_conf, default_dpi,
                default_pages, default_series, memo, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,'active',?,?)""",
            (brand_id, name, url.strip(), source_type, float(default_conf), int(default_dpi),
             default_pages or "", default_series or "_unknown", memo or "", now, now),
        )
    except sqlite3.IntegrityError as e:
        raise DuplicateUrl(url) from e
    return cur.lastrowid


_DOC_EDITABLE = {"name", "memo", "default_conf", "default_dpi", "default_pages", "default_series"}


def update_document(cx: sqlite3.Connection, doc_id: int, **fields) -> None:
    if "brand_raw" in fields:
        fields["brand_id"] = upsert_brand(cx, fields.pop("brand_raw"))
    cols = {k: v for k, v in fields.items() if k in _DOC_EDITABLE or k == "brand_id"}
    if not cols:
        return
    sets = ", ".join(f"{k}=?" for k in cols)
    cx.execute(f"UPDATE document SET {sets}, updated_at=? WHERE id=?",
               (*cols.values(), _now(), doc_id))


def archive_document(cx: sqlite3.Connection, doc_id: int) -> None:
    cx.execute("UPDATE document SET status='archived', updated_at=? WHERE id=?", (_now(), doc_id))


def create_run(cx: sqlite3.Connection, document_id: int, conf: float, dpi: int, pages: str) -> int:
    cur = cx.execute(
        """INSERT INTO run (document_id, conf, dpi, pages, status, started_at)
           VALUES (?,?,?,?, 'QUEUED', ?)""",
        (document_id, float(conf), int(dpi), pages or "", _now()),
    )
    return cur.lastrowid


def attach_dagster_run(cx: sqlite3.Connection, run_id: int, dagster_run_id: str) -> None:
    cx.execute("UPDATE run SET dagster_run_id=?, status='RUNNING' WHERE id=?",
               (dagster_run_id, run_id))


def finish_run(cx: sqlite3.Connection, run_id: int, status: str,
               extracted: int = 0, error: str | None = None) -> None:
    cx.execute("UPDATE run SET status=?, extracted=?, error=?, finished_at=? WHERE id=?",
               (status, int(extracted), error, _now(), run_id))


def record_image(cx: sqlite3.Connection, rec: dict, document_id: int,
                 run_id: int | None) -> None:
    """수집 레코드 1건을 image + image_origin 에 기록. 재수집해도 부풀지 않는다.

    이미 있는 이미지의 라벨은 덮어쓰지 않는다 — 사람이 검수해 고친 값을 재수집이 되돌리면 안 된다.
    """
    now = _now()
    h = rec["content_hash"]
    ext = (rec.get("path") or "").rsplit(".", 1)[-1] or "png"
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, surface, model, modality,
                              review_state, stage, rel_path, created_at)
           VALUES (?,?,?,?,?,?,?, 'pending', 'review', ?, ?)
           ON CONFLICT(content_hash) DO NOTHING""",
        (h, ext, rec.get("brand"), rec.get("series"), rec.get("surface"),
         rec.get("model"), rec.get("modality"), rec.get("path"), now),
    )
    bbox = rec.get("bbox")
    cx.execute(
        """INSERT INTO image_origin (content_hash, document_id, run_id, page_no, bbox, created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(content_hash, document_id) DO NOTHING""",
        (h, document_id, run_id, rec.get("page_no"),
         json.dumps(bbox) if bbox is not None else None, now),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_writes.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add drheri_pipeline/db/writes.py tests/test_writes.py
git commit -m "feat: 운영 DB 쓰기 계층 추가 (브랜드/문서/런/이미지 출처)"
```

---

### Task 3: 읽기 계층 — 퍼널 집계와 트리

**Files:**
- Create: `drheri_pipeline/db/queries.py`
- Test: `tests/test_queries.py`

**Interfaces:**
- Consumes: `db.conn.session`, `db.writes`
- Produces:
  - `queries.funnel_for_document(cx, doc_id: int) -> dict` — 키 `extracted/training/rejected/pending/unreviewed/label_incomplete`
  - `queries.source_tree(cx) -> list[dict]` — `[{brand_id, brand, funnel, documents:[{id,name,url,source_type,funnel,last_run_at,last_run_status}]}]`
  - `queries.document_detail(cx, doc_id: int) -> dict | None` — 문서 메타 + `funnel` + `runs`
  - `queries.overview(cx) -> dict` — `{funnel, recent_runs}`
  - `queries.find_document_by_url(cx, url: str) -> dict | None`
  - `queries.running_runs(cx) -> list[dict]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_queries.py`:

```python
from drheri_pipeline.db import conn, queries, writes


def _seed(cx):
    doc = writes.create_document(
        cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
        source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
        default_pages="", default_series="_unknown", memo="")
    rows = [
        ("pending", "review", "_unknown"),      # 미검수 → 대기
        ("kept", "review", "_unknown"),         # keep 했지만 라벨 미완 → 대기
        ("kept", "training", "TSIII4010S"),     # 학습
        ("rejected", "rejected", "_unknown"),   # 버림
    ]
    for i, (state, stage, model) in enumerate(rows):
        cx.execute(
            """INSERT INTO image (content_hash, ext, brand, series, model, modality,
                                  review_state, stage, rel_path, created_at)
               VALUES (?,'png','Osstem','TSIII',?,'catalog',?,?,?,'2026-07-20T00:00:00+00:00')""",
            (f"h{i}", model, state, stage, f"review/h{i}.png"))
        cx.execute(
            """INSERT INTO image_origin (content_hash, document_id, created_at)
               VALUES (?,?,'2026-07-20T00:00:00+00:00')""", (f"h{i}", doc))
    return doc


def test_funnel_counts(data_root):
    with conn.session() as cx:
        doc = _seed(cx)
        f = queries.funnel_for_document(cx, doc)
    assert f["extracted"] == 4
    assert f["training"] == 1
    assert f["rejected"] == 1
    assert f["pending"] == 2                 # 추출 - 학습 - 버림
    assert f["unreviewed"] == 1
    assert f["label_incomplete"] == 1


def test_source_tree_rolls_up_to_brand(data_root):
    with conn.session() as cx:
        _seed(cx)
        tree = queries.source_tree(cx)
    assert len(tree) == 1
    assert tree[0]["brand"] == "OSSTEM IMPLANT"
    assert tree[0]["funnel"]["extracted"] == 4
    assert len(tree[0]["documents"]) == 1


def test_archived_document_excluded_from_tree(data_root):
    with conn.session() as cx:
        doc = _seed(cx)
        writes.archive_document(cx, doc)
        tree = queries.source_tree(cx)
    assert tree == []


def test_find_document_by_url(data_root):
    with conn.session() as cx:
        _seed(cx)
        hit = queries.find_document_by_url(cx, " https://ex.com/a.pdf ")
        miss = queries.find_document_by_url(cx, "https://ex.com/zzz.pdf")
    assert hit["name"] == "TS"
    assert miss is None
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_queries.py -v`
Expected: FAIL — `ImportError: cannot import name 'queries' from 'drheri_pipeline.db'`

- [ ] **Step 3: 구현**

`drheri_pipeline/db/queries.py`:

```python
"""운영 DB 읽기 — 퍼널 집계와 화면용 조회.

퍼널 정의(스펙 §5.1):
  추출 = 해당 문서의 image_origin 행 수
  학습 = 그중 stage='training'
  버림 = 그중 review_state='rejected'
  대기 = 추출 - 학습 - 버림   (뺄셈 정의 — 어느 칸에도 안 잡히는 건이 생기지 않게)
"""
from __future__ import annotations

import sqlite3

_FUNNEL_SELECT = """
  COUNT(*)                                                     AS extracted,
  SUM(CASE WHEN i.stage='training'        THEN 1 ELSE 0 END)   AS training,
  SUM(CASE WHEN i.review_state='rejected' THEN 1 ELSE 0 END)   AS rejected,
  SUM(CASE WHEN i.review_state='pending'  THEN 1 ELSE 0 END)   AS unreviewed,
  SUM(CASE WHEN i.review_state='kept' AND i.stage<>'training'
                                          THEN 1 ELSE 0 END)   AS label_incomplete
"""

EMPTY_FUNNEL = {"extracted": 0, "training": 0, "rejected": 0,
                "pending": 0, "unreviewed": 0, "label_incomplete": 0}


def _funnel(row: sqlite3.Row | None) -> dict:
    if row is None or not row["extracted"]:
        return dict(EMPTY_FUNNEL)
    extracted = row["extracted"] or 0
    training = row["training"] or 0
    rejected = row["rejected"] or 0
    return {
        "extracted": extracted,
        "training": training,
        "rejected": rejected,
        "pending": extracted - training - rejected,
        "unreviewed": row["unreviewed"] or 0,
        "label_incomplete": row["label_incomplete"] or 0,
    }


def funnel_for_document(cx: sqlite3.Connection, doc_id: int) -> dict:
    row = cx.execute(
        f"""SELECT {_FUNNEL_SELECT}
            FROM image_origin o JOIN image i ON i.content_hash = o.content_hash
            WHERE o.document_id = ?""", (doc_id,)).fetchone()
    return _funnel(row)


def _add(a: dict, b: dict) -> dict:
    return {k: a[k] + b[k] for k in a}


def source_tree(cx: sqlite3.Connection) -> list[dict]:
    """브랜드 › 문서 트리. 보관(archived) 문서는 제외한다."""
    docs = cx.execute(
        """SELECT d.id, d.name, d.url, d.source_type,
                  b.id AS brand_id, b.name_norm AS brand,
                  (SELECT started_at FROM run r WHERE r.document_id=d.id
                    ORDER BY r.started_at DESC LIMIT 1) AS last_run_at,
                  (SELECT status FROM run r WHERE r.document_id=d.id
                    ORDER BY r.started_at DESC LIMIT 1) AS last_run_status
           FROM document d JOIN brand b ON b.id = d.brand_id
           WHERE d.status = 'active'
           ORDER BY b.name_norm, d.name""").fetchall()

    groups: dict[int, dict] = {}
    order: list[int] = []
    for d in docs:
        if d["brand_id"] not in groups:
            groups[d["brand_id"]] = {"brand_id": d["brand_id"], "brand": d["brand"],
                                     "funnel": dict(EMPTY_FUNNEL), "documents": []}
            order.append(d["brand_id"])
        g = groups[d["brand_id"]]
        f = funnel_for_document(cx, d["id"])
        g["documents"].append({
            "id": d["id"], "name": d["name"], "url": d["url"],
            "source_type": d["source_type"], "funnel": f,
            "last_run_at": d["last_run_at"], "last_run_status": d["last_run_status"]})
        g["funnel"] = _add(g["funnel"], f)
    return [groups[i] for i in order]


def document_detail(cx: sqlite3.Connection, doc_id: int) -> dict | None:
    d = cx.execute(
        """SELECT d.*, b.name_norm AS brand, b.name_raw AS brand_raw
           FROM document d JOIN brand b ON b.id = d.brand_id WHERE d.id = ?""",
        (doc_id,)).fetchone()
    if d is None:
        return None
    runs = cx.execute(
        """SELECT id, dagster_run_id, conf, dpi, pages, status, extracted,
                  started_at, finished_at, error
           FROM run WHERE document_id = ? ORDER BY started_at DESC""", (doc_id,)).fetchall()
    return {**dict(d), "funnel": funnel_for_document(cx, doc_id),
            "runs": [dict(r) for r in runs]}


def overview(cx: sqlite3.Connection) -> dict:
    row = cx.execute(
        f"""SELECT {_FUNNEL_SELECT}
            FROM image_origin o JOIN image i ON i.content_hash = o.content_hash""").fetchone()
    runs = cx.execute(
        """SELECT r.id, r.status, r.extracted, r.started_at, r.finished_at,
                  d.id AS document_id, d.name AS document_name
           FROM run r JOIN document d ON d.id = r.document_id
           ORDER BY r.started_at DESC LIMIT 20""").fetchall()
    return {"funnel": _funnel(row), "recent_runs": [dict(r) for r in runs]}


def find_document_by_url(cx: sqlite3.Connection, url: str) -> dict | None:
    row = cx.execute(
        """SELECT d.id, d.name, d.status, b.name_norm AS brand
           FROM document d JOIN brand b ON b.id = d.brand_id WHERE d.url = ?""",
        ((url or "").strip(),)).fetchone()
    return dict(row) if row else None


def running_runs(cx: sqlite3.Connection) -> list[dict]:
    rows = cx.execute(
        """SELECT id, document_id, dagster_run_id, started_at
           FROM run WHERE status IN ('QUEUED','RUNNING')""").fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_queries.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add drheri_pipeline/db/queries.py tests/test_queries.py
git commit -m "feat: 퍼널 집계와 소스 트리 조회 추가"
```

---

### Task 4: jsonl → SQLite 백필 스크립트

기존 `data/manifest.jsonl` 과 `data/sources.jsonl` 을 DB 로 옮긴다. 운영 데이터라 **멱등**이어야 하고 여러 번 돌려도 행 수가 변하면 안 된다.

기존 manifest 의 `origin_url` 은 `https://.../a.pdf#page=3` 형태이므로 `#page=` 앞부분이 문서 URL 이다. `sources.jsonl` 에 없고 manifest 에만 있는 URL 은 문서를 새로 만든다(이름은 URL 의 파일명).

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/backfill_db.py`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `storage.latest_by_hash`, `db.conn.migrate`, `db.conn.session`, `db.writes.create_document`, `db.writes.record_image`
- Produces: `backfill_db.backfill() -> dict` — `{"brands": n, "documents": n, "runs": n, "images": n, "origins": n}` (이번 실행으로 늘어난 행 수)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_backfill.py`:

```python
import json

from drheri_pipeline import storage
from drheri_pipeline.db import conn
from scripts import backfill_db


def _write_fixtures(root):
    manifest = [
        {"content_hash": "h1", "path": "review/a/h1.png", "stage": "review",
         "brand": "Osstem", "series": "_unknown", "model": "_unknown",
         "modality": "catalog", "origin_url": "https://ex.com/a.pdf#page=3",
         "page_no": 3, "bbox": [1, 2, 3, 4], "fetched_at": "2026-07-06T05:43:00+00:00"},
        {"content_hash": "h2", "path": "training/a/h2.png", "stage": "training",
         "brand": "Osstem", "series": "TSIII", "model": "TSIII4010S",
         "modality": "catalog", "origin_url": "https://ex.com/a.pdf#page=4",
         "page_no": 4, "bbox": [5, 6, 7, 8], "approved_at": "2026-07-07T00:00:00+00:00"},
    ]
    (root / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r) for r in manifest) + "\n", encoding="utf-8")
    sources = [{"id": "s1", "url": "https://ex.com/a.pdf", "brand": "Osstem",
                "conf": 0.35, "dpi": 200, "pages": "", "status": "SUCCESS",
                "figures": 2, "created_at": "2026-07-06T05:43:00+00:00"}]
    (root / "sources.jsonl").write_text(
        "\n".join(json.dumps(r) for r in sources) + "\n", encoding="utf-8")


def test_backfill_imports_everything(data_root):
    _write_fixtures(storage.DATA_ROOT)
    stats = backfill_db.backfill()
    assert stats["documents"] == 1
    assert stats["images"] == 2
    with conn.session() as cx:
        img = cx.execute("SELECT * FROM image WHERE content_hash='h2'").fetchone()
    assert img["stage"] == "training"
    assert img["review_state"] == "kept"       # training 이었으면 이미 승인된 것


def test_backfill_is_idempotent(data_root):
    _write_fixtures(storage.DATA_ROOT)
    backfill_db.backfill()
    backfill_db.backfill()
    with conn.session() as cx:
        counts = {t: cx.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
                  for t in ("brand", "document", "run", "image", "image_origin")}
    assert counts == {"brand": 1, "document": 1, "run": 1, "image": 2, "image_origin": 2}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts'`
(`scripts/__init__.py` 를 만든 뒤 다시 돌리면 `ImportError: cannot import name 'backfill_db'` 로 바뀐다. 둘 다 정상적인 실패다.)

- [ ] **Step 3: 구현**

`scripts/__init__.py` 는 빈 파일로 생성한다.

`scripts/backfill_db.py`:

```python
"""manifest.jsonl / sources.jsonl → SQLite 최초 백필 (멱등).

실행: DATA_ROOT=/path/to/data .venv/bin/python -m scripts.backfill_db
"""
from __future__ import annotations

import json

from drheri_pipeline import storage
from drheri_pipeline.db import conn, writes

_TABLES = ("brand", "document", "run", "image", "image_origin")


def _doc_url(origin_url: str | None) -> str:
    return (origin_url or "").split("#page=")[0].strip()


def _read_sources() -> list[dict]:
    p = storage.DATA_ROOT / "sources.jsonl"
    if not p.exists():
        return []
    latest: dict[str, dict] = {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                latest[r["id"]] = r          # append-only — 뒤가 최신
    return list(latest.values())


def _ensure_document(cx, url: str, brand: str, entry: dict | None) -> int:
    row = cx.execute("SELECT id FROM document WHERE url=?", (url,)).fetchone()
    if row:
        return row["id"]
    e = entry or {}
    return writes.create_document(
        cx, brand_raw=brand or "_unknown", name=url.rsplit("/", 1)[-1] or url, url=url,
        source_type="catalog_pdf",
        default_conf=float(e.get("conf") or 0.35),
        default_dpi=int(e.get("dpi") or 200),
        default_pages=e.get("pages") or "",
        default_series=e.get("series") or "_unknown",
        memo="")


def _counts(cx) -> dict:
    return {t: cx.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in _TABLES}


def backfill() -> dict:
    conn.migrate()
    manifest = storage.latest_by_hash()          # content_hash 별 최신 레코드
    sources = _read_sources()

    with conn.session() as cx:
        before = _counts(cx)

        # 1) sources.jsonl → document + run
        for s in sources:
            url = (s.get("url") or "").strip()
            if not url:
                continue
            doc_id = _ensure_document(cx, url, s.get("brand") or "Osstem", s)
            dup = cx.execute("SELECT id FROM run WHERE document_id=? AND started_at=?",
                             (doc_id, s.get("created_at") or "")).fetchone()
            if dup:
                continue
            cx.execute(
                """INSERT INTO run (document_id, dagster_run_id, conf, dpi, pages,
                                    status, extracted, started_at, finished_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (doc_id, s.get("run_id"), float(s.get("conf") or 0.35),
                 int(s.get("dpi") or 200), s.get("pages") or "",
                 s.get("status") or "SUCCESS", int(s.get("figures") or 0),
                 s.get("created_at") or "", s.get("updated_at")))

        # 2) manifest → image + image_origin
        for rec in manifest.values():
            url = _doc_url(rec.get("origin_url"))
            if not url:
                continue
            doc_id = _ensure_document(cx, url, rec.get("brand") or "_unknown", None)
            writes.record_image(cx, rec, doc_id, None)
            if rec.get("stage") == "training":
                cx.execute(
                    """UPDATE image SET stage='training', review_state='kept',
                       reviewed_at=COALESCE(reviewed_at, ?) WHERE content_hash=?""",
                    (rec.get("approved_at") or rec.get("fetched_at"), rec["content_hash"]))

        after = _counts(cx)

    return {"brands": after["brand"] - before["brand"],
            "documents": after["document"] - before["document"],
            "runs": after["run"] - before["run"],
            "images": after["image"] - before["image"],
            "origins": after["image_origin"] - before["image_origin"]}


if __name__ == "__main__":
    print(backfill())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_backfill.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 전체 테스트 실행**

Run: `.venv/bin/python -m pytest tests -v`
Expected: PASS (14 passed)

- [ ] **Step 6: 커밋**

```bash
git add scripts/__init__.py scripts/backfill_db.py tests/test_backfill.py
git commit -m "feat: manifest/sources jsonl 을 SQLite 로 백필하는 스크립트 추가"
```

---

### Task 5: 수집 잡이 SQLite 에 기록하게 변경

Dagster 자산이 `manifest.jsonl` 대신 DB 에 쓴다. UI 가 만든 `document_id`/`ui_run_id` 를 Config 로 받아, 어떤 문서·어떤 런의 결과인지 DB 에 연결한다. manifest 쓰기는 남겨둔다 — 백필 재실행과 롤백 대비용 로그로만 쓰고, 진실의 원천은 DB 다.

**Files:**
- Modify: `drheri_pipeline/config.py`
- Modify: `drheri_pipeline/assets.py`
- Test: `tests/test_ingest_recording.py`

**Interfaces:**
- Consumes: `db.writes.record_image`, `db.writes.finish_run`, `db.conn.session`
- Produces:
  - `assets.record_ingest(records: list[dict], document_id: int, ui_run_id: int | None) -> int` — DB 기록 후 기록된 이미지 수 반환
  - `CatalogPdfConfig.document_id: int`, `CatalogPdfConfig.ui_run_id: int`
  - `SiteXrayConfig.document_id: int`, `SiteXrayConfig.ui_run_id: int`
  - (0 은 "UI 를 거치지 않은 직접 실행" 을 뜻하고, 이때 DB 기록은 건너뛴다)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ingest_recording.py`:

```python
from drheri_pipeline import assets
from drheri_pipeline.db import conn, queries, writes

RECORDS = [
    {"content_hash": "a1", "path": "review/x/a1.png", "brand": "Osstem",
     "series": "_unknown", "surface": None, "model": "_unknown",
     "modality": "catalog", "page_no": 1, "bbox": [0, 0, 10, 10]},
    {"content_hash": "a2", "path": "review/x/a2.png", "brand": "Osstem",
     "series": "_unknown", "surface": None, "model": "_unknown",
     "modality": "catalog", "page_no": 2, "bbox": [0, 0, 10, 10]},
]


def _doc_and_run():
    with conn.session() as cx:
        doc = writes.create_document(
            cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
            source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
            default_pages="", default_series="_unknown", memo="")
        run = writes.create_run(cx, doc, 0.35, 200, "")
    return doc, run


def test_record_ingest_writes_images_and_origins(data_root):
    doc, run = _doc_and_run()
    n = assets.record_ingest(RECORDS, doc, run)
    assert n == 2
    with conn.session() as cx:
        f = queries.funnel_for_document(cx, doc)
    assert f["extracted"] == 2
    assert f["pending"] == 2


def test_record_ingest_skips_when_no_document(data_root):
    assert assets.record_ingest(RECORDS, 0, 0) == 0
    with conn.session() as cx:
        n = cx.execute("SELECT COUNT(*) c FROM image").fetchone()["c"]
    assert n == 0


def test_record_ingest_is_idempotent_on_recollect(data_root):
    doc, run = _doc_and_run()
    assets.record_ingest(RECORDS, doc, run)
    assets.record_ingest(RECORDS, doc, run)
    with conn.session() as cx:
        f = queries.funnel_for_document(cx, doc)
    assert f["extracted"] == 2
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_ingest_recording.py -v`
Expected: FAIL — `AttributeError: module 'drheri_pipeline.assets' has no attribute 'record_ingest'`

- [ ] **Step 3: Config 에 식별자 추가**

`drheri_pipeline/config.py` 의 두 클래스에 아래 두 필드를 각각 추가한다 (기존 필드는 그대로 둔다).

`SiteXrayConfig` 의 `limit: int = 0` 아래에 추가:

```python
    document_id: int = 0           # UI 가 만든 document.id (0 = UI 미경유 직접 실행)
    ui_run_id: int = 0             # UI 가 만든 run.id (0 = UI 미경유)
```

`CatalogPdfConfig` 의 `pages: str = ""` 아래에 추가:

```python
    document_id: int = 0           # UI 가 만든 document.id (0 = UI 미경유 직접 실행)
    ui_run_id: int = 0             # UI 가 만든 run.id (0 = UI 미경유)
```

- [ ] **Step 4: 자산에 DB 기록 붙이기**

`drheri_pipeline/assets.py` 를 아래 내용으로 교체한다.
**주의: 이 파일에 `from __future__ import annotations` 를 추가하면 Dagster Config 해석이 깨진다.**

```python
"""Dagster 자산 + 잡 — 두 수집 경로(site_xray / catalog_pdf).

각 자산: 소스 수집 → review 저장 → SQLite 기록 → FiftyOne 등록.
URL 등 파라미터는 Config(=UI 또는 Launchpad 입력)로 받는다.

주의: 이 모듈은 `from __future__ import annotations` 를 쓰지 않는다 —
그게 `config: SiteXrayConfig` 를 문자열 annotation 으로 만들어 Dagster Config 해석이 실패한다.
"""
from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset, define_asset_job

from . import review, storage
from .config import CatalogPdfConfig, SiteXrayConfig
from .db import conn as db_conn
from .db import writes as db_writes
from .sources import catalog_pdf, site_xray


def record_ingest(records: list, document_id: int, ui_run_id: int) -> int:
    """수집 결과를 운영 DB(image + image_origin)에 기록. document_id 가 0이면 건너뛴다."""
    if not records or not document_id:
        return 0
    db_conn.migrate()
    with db_conn.session() as cx:
        for r in records:
            db_writes.record_image(cx, r, document_id, ui_run_id or None)
    return len(records)


@asset(group_name="ingest", description="whatimplantisthat API 기반 Osstem X-ray 수집 → review")
def site_xray_images(context: AssetExecutionContext, config: SiteXrayConfig) -> MaterializeResult:
    records = site_xray.ingest(config, log=context.log.info)
    storage.append_manifest(records)                 # 롤백 대비 로그 (진실의 원천은 DB)
    recorded = record_ingest(records, config.document_id, config.ui_run_id)
    review.register_fiftyone(records, log=context.log.info)
    return MaterializeResult(metadata={
        "review_count": len(records),
        "recorded_count": recorded,
        "brand": config.brand,
        "modality": config.modality,
        "sample_paths": MetadataValue.json([r["path"] for r in records[:5]]),
    })


@asset(group_name="ingest", description="카탈로그 PDF URL → DocLayout 추출 → review")
def catalog_pdf_images(context: AssetExecutionContext, config: CatalogPdfConfig) -> MaterializeResult:
    records = catalog_pdf.ingest(config, log=context.log.info)
    storage.append_manifest(records)                 # 롤백 대비 로그 (진실의 원천은 DB)
    recorded = record_ingest(records, config.document_id, config.ui_run_id)
    review.register_fiftyone(records, log=context.log.info)
    return MaterializeResult(metadata={
        "review_count": len(records),
        "recorded_count": recorded,
        "brand": config.brand,
        "pdf_url": config.pdf_url,
        "sample_paths": MetadataValue.json([r["path"] for r in records[:5]]),
    })


ingest_site_xray_job = define_asset_job("ingest_site_xray", selection=["site_xray_images"])
ingest_catalog_pdf_job = define_asset_job("ingest_catalog_pdf", selection=["catalog_pdf_images"])
```

`auto_approve` 분기를 제거했다. 승급은 이제 검수 동기화(Task 9)만 담당한다. `config.py` 의 `auto_approve` 필드는 하위호환을 위해 남겨두되 자산에서는 쓰지 않는다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_ingest_recording.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Dagster 정의가 여전히 로드되는지 확인**

Run: `.venv/bin/python -c "from drheri_pipeline.definitions import defs; print(sorted(a.key.to_user_string() for a in defs.get_asset_graph().assets_defs))"`
Expected: `['catalog_pdf_images', 'site_xray_images']`

- [ ] **Step 7: 커밋**

```bash
git add drheri_pipeline/config.py drheri_pipeline/assets.py tests/test_ingest_recording.py
git commit -m "feat: 수집 잡이 SQLite 에 이미지와 출처를 기록하도록 변경"
```

---

### Task 6: FiftyOne 제어 — 정지·좀비정리·기동·헬스체크

과거에 앱 하나당 파이썬 프로세스가 여러 개 남아 데이터셋이 주기적으로 초기화되던 문제가 있었다. 재기동은 반드시 4단계를 밟고, 수동 버튼과 수집 완료 훅이 **같은 함수 하나**를 호출한다.

**Files:**
- Create: `drheri_pipeline/services/__init__.py`
- Create: `drheri_pipeline/services/fiftyone_ctl.py`
- Test: `tests/test_fiftyone_ctl.py`

**Interfaces:**
- Consumes: `subprocess`, `urllib.request`
- Produces:
  - `fiftyone_ctl.stop() -> list[str]` — 실행한 명령들의 요약
  - `fiftyone_ctl.kill_orphans() -> int` — 종료시킨 잔여 프로세스 수
  - `fiftyone_ctl.start() -> None`
  - `fiftyone_ctl.health() -> dict` — `{"ok": bool, "port": int, "detail": str}`
  - `fiftyone_ctl.restart() -> dict` — `{"ok": bool, "orphans_killed": int, "detail": str}`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_fiftyone_ctl.py`:

```python
from drheri_pipeline.services import fiftyone_ctl


def test_kill_orphans_uses_bracket_patterns_and_spares_mongod(monkeypatch):
    """포트 기준 kill 금지, 자기 자신 매치 방지(브래킷), mongod 보존을 커맨드로 검증."""
    calls = []

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(fiftyone_ctl.subprocess, "run",
                        lambda cmd, **kw: (calls.append(cmd), R())[1])
    fiftyone_ctl.kill_orphans()

    joined = " ".join(" ".join(c) for c in calls)
    assert "mongod" not in joined            # mongod 는 절대 죽이지 않는다
    assert "fuser" not in joined and "lsof" not in joined   # 포트 기준 kill 금지
    for pat in fiftyone_ctl.ORPHAN_PATTERNS:
        assert pat in joined
        assert pat.startswith("[")           # pkill 자기 자신 매치 방지


def test_restart_reports_failure_when_health_fails(monkeypatch):
    monkeypatch.setattr(fiftyone_ctl, "stop", lambda: ["stopped"])
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: 3)
    monkeypatch.setattr(fiftyone_ctl, "start", lambda: None)
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda: {"ok": False, "port": 5151, "detail": "연결 거부"})
    out = fiftyone_ctl.restart()
    assert out["ok"] is False
    assert out["orphans_killed"] == 3
    assert "연결 거부" in out["detail"]


def test_restart_succeeds_when_health_ok(monkeypatch):
    monkeypatch.setattr(fiftyone_ctl, "stop", lambda: ["stopped"])
    monkeypatch.setattr(fiftyone_ctl, "kill_orphans", lambda: 0)
    monkeypatch.setattr(fiftyone_ctl, "start", lambda: None)
    monkeypatch.setattr(fiftyone_ctl, "health",
                        lambda: {"ok": True, "port": 5151, "detail": "OK"})
    assert fiftyone_ctl.restart()["ok"] is True
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_fiftyone_ctl.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drheri_pipeline.services'`

- [ ] **Step 3: 구현**

`drheri_pipeline/services/__init__.py` 는 빈 파일로 생성한다.

`drheri_pipeline/services/fiftyone_ctl.py`:

```python
"""FiftyOne 서비스 제어 — 정지 → 좀비정리 → 기동 → 헬스체크.

과거 사고: 앱 하나당 파이썬 프로세스가 여러 개 남아, 포트만 죽이는 방식으로는
자식 세션이 살아남아 데이터셋이 주기적으로 초기화됐다. 그래서
  - 포트 기준 kill(fuser/lsof) 을 쓰지 않는다
  - cmdline 패턴으로 프로세스 트리를 잡는다
  - pkill 이 자기 자신을 매치하지 않도록 브래킷 표기를 쓴다
  - mongod 는 절대 죽이지 않는다 (데이터 유실)
"""
from __future__ import annotations

import os
import subprocess
import urllib.error
import urllib.request

SERVICE = os.getenv("FIFTYONE_SERVICE", "drheri-fiftyone")
PORT = int(os.getenv("FIFTYONE_PORT", "5151"))
HEALTH_URL = os.getenv("FIFTYONE_HEALTH_URL", f"http://127.0.0.1:{PORT}/")

# 브래킷 표기: pkill -f "[f]iftyone.server" 는 자기 자신의 cmdline 과 매치되지 않는다.
ORPHAN_PATTERNS = ["[f]iftyone.server", "[f]iftyone.core.service", "[s]erve_fiftyone_service"]


def _run(cmd: list[str], timeout: int = 60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def stop() -> list[str]:
    r = _run(["sudo", "-n", "systemctl", "stop", SERVICE], timeout=90)
    return [f"systemctl stop {SERVICE} → rc={r.returncode} {(r.stderr or '').strip()[:120]}"]


def kill_orphans() -> int:
    """cmdline 패턴으로 잔여 프로세스를 종료. 종료시킨 패턴 수를 반환."""
    killed = 0
    for pat in ORPHAN_PATTERNS:
        r = _run(["pkill", "-TERM", "-f", pat])
        if r.returncode == 0:                 # 0 = 하나 이상 종료됨
            killed += 1
    for pat in ORPHAN_PATTERNS:               # TERM 으로 안 죽은 것만 KILL
        _run(["pkill", "-KILL", "-f", pat])
    return killed


def start() -> None:
    _run(["sudo", "-n", "systemctl", "start", SERVICE], timeout=90)


def health() -> dict:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=10) as resp:
            ok = 200 <= resp.status < 400
            return {"ok": ok, "port": PORT, "detail": f"HTTP {resp.status}"}
    except urllib.error.URLError as e:
        return {"ok": False, "port": PORT, "detail": f"연결 실패: {e.reason}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "port": PORT, "detail": f"{e.__class__.__name__}: {e}"}


def restart() -> dict:
    """정지 → 좀비정리 → 기동 → 헬스체크. 수동 버튼과 완료 훅이 공유하는 유일한 경로."""
    detail = stop()
    orphans = kill_orphans()
    start()
    h = health()
    detail.append(f"잔여 프로세스 정리 {orphans}건")
    detail.append(h["detail"])
    return {"ok": h["ok"], "orphans_killed": orphans, "detail": " / ".join(detail)}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_fiftyone_ctl.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 개발서버에서 실제 재기동 검증 (수동)**

개발서버(58.229.105.3)에서 실행한다.

```bash
cd ~/Dr.HERi/data-pipeline
FIFTYONE_DATABASE_VALIDATION=false .venv/bin/python -c \
  "from drheri_pipeline.services import fiftyone_ctl; print(fiftyone_ctl.restart())"
pgrep -af "[f]iftyone" | wc -l
```
Expected: `{'ok': True, ...}` 그리고 두 번째 명령이 서비스 프로세스 1개만 보고할 것.
mongod 는 계속 살아 있어야 한다: `pgrep -af mongod` 가 결과를 반환.

- [ ] **Step 6: 커밋**

```bash
git add drheri_pipeline/services tests/test_fiftyone_ctl.py
git commit -m "feat: FiftyOne 재기동 절차 추가 (좀비 프로세스 정리 포함)"
```

---

### Task 7: 검수 동기화 — 판정 + 라벨 + 승급

FiftyOne 에서 찍은 `keep`/`reject` 태그와 수정된 라벨을 SQLite 로 가져오고, 조건을 만족하면 training 으로 승급한다. 기존 `scripts/promote_reviewed.py` 를 흡수한다.

FiftyOne 은 무거운 의존성이므로 데이터 읽기를 `read_review_state()` 하나로 격리하고, 테스트는 이 함수를 대체(monkeypatch)해서 순수 로직만 검증한다.

**Files:**
- Create: `drheri_pipeline/services/sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `db.conn.session`, `storage.stage_image_path`, `storage.rel`, `taxonomy.normalize_brand`
- Produces:
  - `sync.read_review_state() -> list[dict]` — `[{content_hash, tags:list[str], brand, series, surface, model}]`
  - `sync.is_promotable(img: dict) -> bool`
  - `sync.run_sync() -> dict` — `{"kept": n, "rejected": n, "promoted": n, "note": str}`

승급 조건은 `review_state == 'kept'` 이면서 `brand`/`series`/`model` 셋 다 비어 있지 않고 `_unknown` 이 아닌 경우다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_sync.py`:

```python
from drheri_pipeline import storage
from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.services import sync


def _seed_images(data_root):
    """review 단계 이미지 3장 + 실제 파일 생성."""
    with conn.session() as cx:
        doc = writes.create_document(
            cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
            source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
            default_pages="", default_series="_unknown", memo="")
        for h in ("k1", "k2", "r1"):
            p = storage.DATA_ROOT / "review" / f"{h}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"png")
            writes.record_image(cx, {
                "content_hash": h, "path": f"review/{h}.png", "brand": "Osstem",
                "series": "_unknown", "surface": None, "model": "_unknown",
                "modality": "catalog", "page_no": 1, "bbox": [0, 0, 1, 1]}, doc, None)
    return doc


def test_is_promotable_requires_all_three_labels():
    assert sync.is_promotable({"review_state": "kept", "brand": "Osstem",
                               "series": "TSIII", "model": "TSIII4010S"}) is True
    assert sync.is_promotable({"review_state": "kept", "brand": "Osstem",
                               "series": "TSIII", "model": "_unknown"}) is False
    assert sync.is_promotable({"review_state": "pending", "brand": "Osstem",
                               "series": "TSIII", "model": "TSIII4010S"}) is False


def test_run_sync_applies_tags_labels_and_promotion(data_root, monkeypatch):
    doc = _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "k1", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": "SA", "model": "TSIII4010S"},
        {"content_hash": "k2", "tags": ["keep"], "brand": "Osstem",
         "series": "TSIII", "surface": None, "model": "_unknown"},
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"},
    ])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)

    out = sync.run_sync()
    assert out["kept"] == 2
    assert out["rejected"] == 1
    assert out["promoted"] == 1

    with conn.session() as cx:
        f = queries.funnel_for_document(cx, doc)
        k1 = cx.execute("SELECT * FROM image WHERE content_hash='k1'").fetchone()
    assert f == {"extracted": 3, "training": 1, "rejected": 1, "pending": 1,
                 "unreviewed": 0, "label_incomplete": 1}
    assert k1["stage"] == "training"
    assert k1["surface"] == "SA"
    assert (storage.DATA_ROOT / k1["rel_path"]).exists()


def test_rejected_file_is_moved_not_deleted(data_root, monkeypatch):
    _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda: [
        {"content_hash": "r1", "tags": ["reject"], "brand": "Osstem",
         "series": "_unknown", "surface": None, "model": "_unknown"}])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)
    sync.run_sync()

    with conn.session() as cx:
        row = cx.execute("SELECT * FROM image WHERE content_hash='r1'").fetchone()
    assert row["stage"] == "rejected"
    assert row["rel_path"].startswith("rejected/")
    assert (storage.DATA_ROOT / row["rel_path"]).exists()      # 삭제가 아니라 이동


def test_sync_log_is_recorded(data_root, monkeypatch):
    _seed_images(data_root)
    monkeypatch.setattr(sync, "read_review_state", lambda: [])
    monkeypatch.setattr(sync, "push_stage_to_fiftyone", lambda moves: None)
    sync.run_sync()
    with conn.session() as cx:
        row = cx.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row["finished_at"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: FAIL — `ImportError: cannot import name 'sync' from 'drheri_pipeline.services'`

- [ ] **Step 3: 구현**

`drheri_pipeline/services/sync.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_sync.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 전체 테스트 실행**

Run: `.venv/bin/python -m pytest tests -v`
Expected: PASS (25 passed)

- [ ] **Step 6: 커밋**

```bash
git add drheri_pipeline/services/sync.py tests/test_sync.py
git commit -m "feat: FiftyOne 검수결과 동기화 추가 (판정·라벨·승급 일괄 처리)"
```

---

### Task 8: DGX 내보내기 — SQLite → labels.tsv / manifest.jsonl

`storage.export_labels_tsv()` 는 manifest 를 읽는다. 진실의 원천이 DB 로 바뀌었으므로 DB 를 읽는 내보내기로 대체한다.

**Files:**
- Create: `drheri_pipeline/services/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `db.conn.session`, `taxonomy.normalize_brand`, `taxonomy.compose_series`
- Produces:
  - `export.export_all() -> dict` — `{"labels_tsv": str, "manifest_jsonl": str, "rows": n}` (경로는 DATA_ROOT 상대)
  - `export.class_distribution(cx) -> dict` — `{"brands": [{name, count}], "series": [...], "models": [...], "total": n}`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_export.py`:

```python
import json

from drheri_pipeline import storage
from drheri_pipeline.db import conn, writes
from drheri_pipeline.services import export


def _seed(cx):
    doc = writes.create_document(
        cx, brand_raw="Osstem", name="TS", url="https://ex.com/a.pdf",
        source_type="catalog_pdf", default_conf=0.35, default_dpi=200,
        default_pages="", default_series="_unknown", memo="")
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, surface, model, modality,
                              review_state, stage, rel_path, created_at)
           VALUES ('t1','png','Osstem','TSIII','SA','TSIII4010S','catalog',
                   'kept','training','training/a/t1.png','2026-07-20T00:00:00+00:00')""")
    cx.execute(
        """INSERT INTO image (content_hash, ext, brand, series, model, modality,
                              review_state, stage, rel_path, created_at)
           VALUES ('p1','png','Osstem','TSIII','_unknown','catalog',
                   'pending','review','review/a/p1.png','2026-07-20T00:00:00+00:00')""")
    for h in ("t1", "p1"):
        cx.execute("""INSERT INTO image_origin (content_hash, document_id, created_at)
                      VALUES (?,?,'2026-07-20T00:00:00+00:00')""", (h, doc))


def test_export_writes_only_training_rows_with_dgx_labels(data_root):
    with conn.session() as cx:
        _seed(cx)
    out = export.export_all()
    assert out["rows"] == 1

    tsv = (storage.DATA_ROOT / out["labels_tsv"]).read_text(encoding="utf-8").splitlines()
    assert tsv[0] == "brand\tseries\tmodel\trel_path"
    assert tsv[1] == "OSSTEM IMPLANT\tTSIII SA\tTSIII4010S\ta/t1.png"   # 정규화 + series 합성

    lines = (storage.DATA_ROOT / out["manifest_jsonl"]).read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["content_hash"] == "t1"


def test_class_distribution_counts_training_only(data_root):
    with conn.session() as cx:
        _seed(cx)
        dist = export.class_distribution(cx)
    assert dist["total"] == 1
    assert dist["brands"] == [{"name": "OSSTEM IMPLANT", "count": 1}]
    assert dist["models"] == [{"name": "TSIII4010S", "count": 1}]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_export.py -v`
Expected: FAIL — `ImportError: cannot import name 'export' from 'drheri_pipeline.services'`

- [ ] **Step 3: 구현**

`drheri_pipeline/services/export.py`:

```python
"""DGX 내보내기 — SQLite 의 training 이미지를 labels.tsv / manifest.jsonl 로 평탄화.

우리 DB 는 brand/series/surface/model 을 분해 저장한다. 내보낼 때만 DGX 표기로
브랜드를 정규화하고 series+surface 를 합성한다(예: 'TSIII'+'SA' → 'TSIII SA').
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from drheri_pipeline import storage
from drheri_pipeline.db import conn
from drheri_pipeline.taxonomy import compose_series, normalize_brand

_TRAINING = "SELECT * FROM image WHERE stage='training' ORDER BY content_hash"


def _dgx_row(r: sqlite3.Row) -> tuple[str, str, str, str]:
    brand = normalize_brand(r["brand"]) or "_unknown"
    series = compose_series(r["series"], r["surface"]) or "_unknown"
    model = r["model"] or "_unknown"
    train_root = storage.DATA_ROOT / "training"
    abs_path = (storage.DATA_ROOT / r["rel_path"]).resolve()
    try:
        rel = abs_path.relative_to(train_root).as_posix()
    except ValueError:                      # training/ 밖이면 DATA_ROOT 기준 경로 그대로
        rel = Path(r["rel_path"]).as_posix()
    return brand, series, model, rel


def export_all() -> dict:
    tsv_path = storage.DATA_ROOT / "training" / "labels.tsv"
    jsonl_path = storage.DATA_ROOT / "export" / "manifest.jsonl"
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    rows = 0
    with conn.session() as cx, \
            tsv_path.open("w", encoding="utf-8") as tsv, \
            jsonl_path.open("w", encoding="utf-8") as jl:
        tsv.write("brand\tseries\tmodel\trel_path\n")
        for r in cx.execute(_TRAINING).fetchall():
            brand, series, model, rel = _dgx_row(r)
            tsv.write(f"{brand}\t{series}\t{model}\t{rel}\n")
            jl.write(json.dumps({**dict(r), "dgx_brand": brand, "dgx_series": series},
                                ensure_ascii=False) + "\n")
            rows += 1

    return {"labels_tsv": storage.rel(tsv_path),
            "manifest_jsonl": storage.rel(jsonl_path),
            "rows": rows}


def class_distribution(cx: sqlite3.Connection) -> dict:
    """training 기준 클래스 분포 (DGX 표기로 집계)."""
    brands: dict[str, int] = {}
    series: dict[str, int] = {}
    models: dict[str, int] = {}
    total = 0
    for r in cx.execute(_TRAINING).fetchall():
        b, s, m, _ = _dgx_row(r)
        brands[b] = brands.get(b, 0) + 1
        series[s] = series.get(s, 0) + 1
        models[m] = models.get(m, 0) + 1
        total += 1

    def _top(d: dict) -> list[dict]:
        return [{"name": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))]

    return {"brands": _top(brands), "series": _top(series), "models": _top(models), "total": total}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_export.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add drheri_pipeline/services/export.py tests/test_export.py
git commit -m "feat: SQLite 기반 DGX 내보내기와 클래스 분포 집계 추가"
```

---

### Task 9: API 봉투와 SSE 브로드캐스터

모든 라우트가 공유하는 두 조각을 먼저 만든다. 봉투는 `{ok,data,error}` 고정이고, SSE 는 수집 완료·동기화 완료를 브라우저로 밀어준다.

**Files:**
- Create: `drheri_pipeline/ui/envelope.py`
- Create: `drheri_pipeline/ui/events.py`
- Test: `tests/test_envelope.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Produces:
  - `envelope.ok(data=None, status: int = 200) -> JSONResponse`
  - `envelope.fail(code: str, message: str, status: int = 400) -> JSONResponse`
  - `envelope.ApiError(code: str, message: str, status: int = 400)` — 예외
  - `envelope.api_error_handler(request, exc) -> JSONResponse`
  - `events.broadcaster` — `Broadcaster` 인스턴스 (싱글턴)
  - `Broadcaster.subscribe() -> asyncio.Queue`, `.unsubscribe(q)`, `.publish(event: str, payload: dict) -> None`, `.sse_stream(q)` — async generator

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_envelope.py`:

```python
import json

from drheri_pipeline.ui import envelope


def _body(resp):
    return json.loads(resp.body.decode("utf-8"))


def test_ok_wraps_data():
    b = _body(envelope.ok({"x": 1}))
    assert b == {"ok": True, "data": {"x": 1}, "error": None}


def test_fail_sets_code_and_status():
    resp = envelope.fail("duplicate_url", "이미 등록된 URL 입니다", status=409)
    assert resp.status_code == 409
    b = _body(resp)
    assert b["ok"] is False
    assert b["error"] == {"code": "duplicate_url", "message": "이미 등록된 URL 입니다"}


def test_api_error_handler_uses_exception_fields():
    exc = envelope.ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    resp = envelope.api_error_handler(None, exc)
    assert resp.status_code == 404
    assert _body(resp)["error"]["code"] == "not_found"
```

`tests/test_events.py`:

```python
import asyncio
import json

import pytest

from drheri_pipeline.ui.events import Broadcaster


@pytest.mark.asyncio
async def test_publish_reaches_all_subscribers():
    b = Broadcaster()
    q1, q2 = b.subscribe(), b.subscribe()
    b.publish("run.finished", {"run_id": 7})
    for q in (q1, q2):
        evt = await asyncio.wait_for(q.get(), timeout=1)
        assert evt["event"] == "run.finished"
        assert evt["payload"] == {"run_id": 7}


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    b = Broadcaster()
    q = b.subscribe()
    b.unsubscribe(q)
    b.publish("run.finished", {})
    assert q.empty()


@pytest.mark.asyncio
async def test_sse_stream_formats_frames():
    b = Broadcaster()
    q = b.subscribe()
    b.publish("sync.finished", {"kept": 2})
    stream = b.sse_stream(q)
    frame = await asyncio.wait_for(stream.__anext__(), timeout=1)
    assert frame.startswith("event: sync.finished\ndata: ")
    assert json.loads(frame.split("data: ", 1)[1].strip()) == {"kept": 2}
    assert frame.endswith("\n\n")
```

`pytest-asyncio` 가 필요하다. `pyproject.toml` 의 `dev` extra 를 다음으로 바꾸고, 파일 끝에 설정을 추가한다.

```toml
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
```

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_envelope.py tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drheri_pipeline.ui.envelope'`

- [ ] **Step 3: 봉투 구현**

`drheri_pipeline/ui/envelope.py`:

```python
"""API 응답 봉투 — 모든 라우트가 {ok, data, error} 로만 응답한다."""
from __future__ import annotations

from starlette.responses import JSONResponse


class ApiError(Exception):
    """라우트에서 던지면 봉투 형태로 변환된다."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def ok(data=None, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data, "error": None}, status_code=status)


def fail(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "data": None,
                         "error": {"code": code, "message": message}}, status_code=status)


def api_error_handler(request, exc: ApiError) -> JSONResponse:
    return fail(exc.code, exc.message, exc.status)


def unhandled_error_handler(request, exc: Exception) -> JSONResponse:
    return fail("internal_error", f"{exc.__class__.__name__}: {exc}", status=500)
```

- [ ] **Step 4: SSE 구현**

`drheri_pipeline/ui/events.py`:

```python
"""SSE 브로드캐스터 — 서버에서 브라우저로 이벤트를 민다(폴링 대체).

이벤트: run.finished, sync.finished, export.finished
"""
from __future__ import annotations

import asyncio
import json

MAX_QUEUE = 100


class Broadcaster:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: str, payload: dict) -> None:
        """느린 구독자 때문에 서버가 막히지 않도록 큐가 차면 그 구독자는 건너뛴다."""
        for q in list(self._subs):
            try:
                q.put_nowait({"event": event, "payload": payload})
            except asyncio.QueueFull:
                continue

    async def sse_stream(self, q: asyncio.Queue):
        """SSE 프레임 생성기. 25초마다 주석 프레임으로 연결을 살려둔다."""
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield (f"event: {evt['event']}\n"
                       f"data: {json.dumps(evt['payload'], ensure_ascii=False)}\n\n")
        finally:
            self.unsubscribe(q)


broadcaster = Broadcaster()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_envelope.py tests/test_events.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml drheri_pipeline/ui/envelope.py drheri_pipeline/ui/events.py \
        tests/test_envelope.py tests/test_events.py
git commit -m "feat: API 응답 봉투와 SSE 브로드캐스터 추가"
```

---

### Task 10: 소스 API — 목록·중복확인·등록·상세·수정·보관

**Files:**
- Create: `drheri_pipeline/ui/api/__init__.py`
- Create: `drheri_pipeline/ui/api/sources.py`
- Test: `tests/test_api_sources.py`

**Interfaces:**
- Consumes: `db.conn.session`, `db.queries`, `db.writes`, `ui.envelope`
- Produces:
  - `sources.routes` — `list[starlette.routing.Route]`
  - 경로: `GET /api/sources`, `GET /api/sources/check`, `POST /api/sources`,
    `GET /api/sources/{doc_id:int}`, `POST /api/sources/{doc_id:int}/update`,
    `POST /api/sources/{doc_id:int}/archive`
  - 등록 본문(JSON): `{url, name?, brand, source_type?, conf?, dpi?, pages?, series?, memo?}`
    — `name` 이 없으면 URL 의 파일명을 쓴다. `source_type` 기본값 `catalog_pdf`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api_sources.py`:

```python
import pytest
from starlette.testclient import TestClient

from drheri_pipeline.ui import app as ui_app


@pytest.fixture()
def client(data_root):
    return TestClient(ui_app.create_app())


def _create(client, url="https://ex.com/a.pdf", brand="Osstem", name="TS 카탈로그"):
    return client.post("/api/sources", json={
        "url": url, "name": name, "brand": brand,
        "conf": 0.35, "dpi": 200, "pages": "", "series": "_unknown", "memo": "메모"})


def test_create_and_list(client):
    r = _create(client)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    doc_id = r.json()["data"]["id"]

    tree = client.get("/api/sources").json()["data"]
    assert tree[0]["brand"] == "OSSTEM IMPLANT"
    assert tree[0]["documents"][0]["id"] == doc_id
    assert tree[0]["documents"][0]["funnel"]["extracted"] == 0


def test_duplicate_url_returns_409_with_existing_id(client):
    first = _create(client).json()["data"]["id"]
    r = _create(client)
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "duplicate_url"
    assert body["data"] is None

    chk = client.get("/api/sources/check", params={"url": " https://ex.com/a.pdf "}).json()
    assert chk["data"]["exists"] is True
    assert chk["data"]["document"]["id"] == first


def test_check_returns_false_for_new_url(client):
    body = client.get("/api/sources/check", params={"url": "https://ex.com/new.pdf"}).json()
    assert body["data"] == {"exists": False, "document": None}


def test_name_defaults_to_filename(client):
    r = client.post("/api/sources", json={"url": "https://ex.com/ts-gs.pdf", "brand": "Osstem"})
    doc_id = r.json()["data"]["id"]
    detail = client.get(f"/api/sources/{doc_id}").json()["data"]
    assert detail["name"] == "ts-gs.pdf"
    assert detail["default_conf"] == 0.35
    assert detail["default_dpi"] == 200


def test_update_and_archive(client):
    doc_id = _create(client).json()["data"]["id"]
    r = client.post(f"/api/sources/{doc_id}/update",
                    json={"name": "새 이름", "memo": "수정됨", "dpi": 300})
    assert r.json()["ok"] is True
    detail = client.get(f"/api/sources/{doc_id}").json()["data"]
    assert detail["name"] == "새 이름"
    assert detail["default_dpi"] == 300

    client.post(f"/api/sources/{doc_id}/archive")
    assert client.get("/api/sources").json()["data"] == []
    assert client.get(f"/api/sources/{doc_id}").json()["data"]["status"] == "archived"


def test_detail_404_for_missing_document(client):
    r = client.get("/api/sources/9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_create_requires_url(client):
    r = client.post("/api/sources", json={"brand": "Osstem"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_api_sources.py -v`
Expected: FAIL — `AttributeError: module 'drheri_pipeline.ui.app' has no attribute 'create_app'`

- [ ] **Step 3: 라우트 구현**

`drheri_pipeline/ui/api/__init__.py` 는 빈 파일로 생성한다.

`drheri_pipeline/ui/api/sources.py`:

```python
"""소스(브랜드 › 문서) API."""
from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.ui.envelope import ApiError, ok

_UPDATE_MAP = {"name": "name", "memo": "memo", "conf": "default_conf",
               "dpi": "default_dpi", "pages": "default_pages", "series": "default_series"}


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        raise ApiError("invalid_request", "JSON 본문을 해석할 수 없습니다") from e
    if not isinstance(body, dict):
        raise ApiError("invalid_request", "JSON 객체가 필요합니다")
    return body


def _list_tree() -> list[dict]:
    with conn.session() as cx:
        return queries.source_tree(cx)


async def list_sources(request: Request):
    return ok(await run_in_threadpool(_list_tree))


async def check_url(request: Request):
    url = (request.query_params.get("url") or "").strip()
    if not url:
        raise ApiError("invalid_request", "url 파라미터가 필요합니다")

    def _find():
        with conn.session() as cx:
            return queries.find_document_by_url(cx, url)

    doc = await run_in_threadpool(_find)
    return ok({"exists": doc is not None, "document": doc})


async def create_source(request: Request):
    body = await _json(request)
    url = (body.get("url") or "").strip()
    if not url:
        raise ApiError("invalid_request", "URL 을 입력하세요")
    brand = (body.get("brand") or "").strip()
    if not brand:
        raise ApiError("invalid_request", "브랜드를 입력하세요")
    name = (body.get("name") or "").strip() or url.rsplit("/", 1)[-1] or url

    def _create():
        with conn.session() as cx:
            return writes.create_document(
                cx, brand_raw=brand, name=name, url=url,
                source_type=body.get("source_type") or "catalog_pdf",
                default_conf=float(body.get("conf") or 0.35),
                default_dpi=int(body.get("dpi") or 200),
                default_pages=body.get("pages") or "",
                default_series=body.get("series") or "_unknown",
                memo=body.get("memo") or "")

    try:
        doc_id = await run_in_threadpool(_create)
    except writes.DuplicateUrl as e:
        raise ApiError("duplicate_url", "이미 등록된 URL 입니다", status=409) from e
    return ok({"id": doc_id})


async def get_source(request: Request):
    doc_id = request.path_params["doc_id"]

    def _detail():
        with conn.session() as cx:
            return queries.document_detail(cx, doc_id)

    detail = await run_in_threadpool(_detail)
    if detail is None:
        raise ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    return ok(detail)


async def update_source(request: Request):
    doc_id = request.path_params["doc_id"]
    body = await _json(request)
    fields = {_UPDATE_MAP[k]: v for k, v in body.items() if k in _UPDATE_MAP}
    if "brand" in body and (body["brand"] or "").strip():
        fields["brand_raw"] = body["brand"].strip()
    if "default_conf" in fields:
        fields["default_conf"] = float(fields["default_conf"])
    if "default_dpi" in fields:
        fields["default_dpi"] = int(fields["default_dpi"])

    def _update():
        with conn.session() as cx:
            if queries.document_detail(cx, doc_id) is None:
                return False
            writes.update_document(cx, doc_id, **fields)
            return True

    if not await run_in_threadpool(_update):
        raise ApiError("not_found", "문서를 찾을 수 없습니다", status=404)
    return ok({"id": doc_id})


async def archive_source(request: Request):
    doc_id = request.path_params["doc_id"]

    def _archive():
        with conn.session() as cx:
            writes.archive_document(cx, doc_id)

    await run_in_threadpool(_archive)
    return ok({"id": doc_id})


routes = [
    Route("/api/sources", list_sources, methods=["GET"]),
    Route("/api/sources/check", check_url, methods=["GET"]),
    Route("/api/sources", create_source, methods=["POST"]),
    Route("/api/sources/{doc_id:int}", get_source, methods=["GET"]),
    Route("/api/sources/{doc_id:int}/update", update_source, methods=["POST"]),
    Route("/api/sources/{doc_id:int}/archive", archive_source, methods=["POST"]),
]
```

- [ ] **Step 4: 앱 팩토리 도입**

`drheri_pipeline/ui/app.py` 전체를 아래로 교체한다. 이 시점에는 Jinja2 화면이 사라지고 API 만 남는다 (화면은 Task 14 에서 붙인다).

```python
"""Dr.HERi 데이터 파이프라인 관리 UI — JSON API + 정적 SPA 서빙.

실행: uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000
"""
from __future__ import annotations

from starlette.applications import Starlette

from drheri_pipeline.db import conn
from drheri_pipeline.ui.api import sources
from drheri_pipeline.ui.envelope import ApiError, api_error_handler, unhandled_error_handler


def create_app() -> Starlette:
    conn.migrate()
    return Starlette(
        routes=[*sources.routes],
        exception_handlers={ApiError: api_error_handler, Exception: unhandled_error_handler},
    )


app = create_app()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_api_sources.py -v`
Expected: PASS (7 passed)

`httpx` 는 이미 의존성에 있으므로 `TestClient` 가 동작한다.

- [ ] **Step 6: 커밋**

```bash
git add drheri_pipeline/ui/api drheri_pipeline/ui/app.py tests/test_api_sources.py
git commit -m "feat: 소스 API 추가 (목록·중복확인·등록·상세·수정·보관)"
```

---

### Task 11: 수집 실행 API + 완료 훅 + SSE 엔드포인트

폴링 루프(`_watch_run`)를 제거하고 세 경로로 대체한다: 실행 제출, Dagster 센서가 때리는 완료 훅, 그리고 놓친 경우를 위한 수동/진입 시 1회 정정.

**Files:**
- Modify: `drheri_pipeline/ui/dagster_client.py`
- Create: `drheri_pipeline/ui/api/runs.py`
- Modify: `drheri_pipeline/ui/app.py`
- Test: `tests/test_api_runs.py`

**Interfaces:**
- Consumes: `db.writes.create_run/attach_dagster_run/finish_run`, `db.queries.running_runs`, `events.broadcaster`, `services.fiftyone_ctl.restart`
- Produces:
  - `dagster_client.submit(pdf_url, brand, series, conf, dpi, pages, document_id, ui_run_id) -> str`
  - `runs.routes` — 경로: `POST /api/sources/{doc_id:int}/collect`,
    `GET /api/sources/{doc_id:int}/runs/latest`, `GET /api/runs/{run_id:int}/log`,
    `POST /api/hooks/run-finished`, `GET /api/events`
  - 훅 본문(JSON): `{ui_run_id: int, dagster_run_id: str, status: "SUCCESS"|"FAILURE", extracted: int, error: str|null}`
  - 훅 인증: 헤더 `X-Hook-Token` 이 환경변수 `HOOK_TOKEN` 과 일치해야 한다 (`HOOK_TOKEN` 미설정이면 `drheri-dev` 를 기본값으로 쓴다)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api_runs.py`:

```python
import pytest
from starlette.testclient import TestClient

from drheri_pipeline.db import conn, queries
from drheri_pipeline.ui import app as ui_app
from drheri_pipeline.ui.api import runs as runs_api


@pytest.fixture()
def client(data_root, monkeypatch):
    monkeypatch.setattr(runs_api.dagster_client, "submit",
                        lambda **kw: "dagster-run-1")
    monkeypatch.setattr(runs_api.fiftyone_ctl, "restart",
                        lambda: {"ok": True, "orphans_killed": 0, "detail": "OK"})
    return TestClient(ui_app.create_app())


def _doc(client):
    return client.post("/api/sources", json={
        "url": "https://ex.com/a.pdf", "brand": "Osstem", "name": "TS"}).json()["data"]["id"]


def test_collect_creates_run_and_returns_ids(client):
    doc = _doc(client)
    r = client.post(f"/api/sources/{doc}/collect", json={"conf": 0.4, "dpi": 300, "pages": "1,2"})
    data = r.json()["data"]
    assert data["dagster_run_id"] == "dagster-run-1"
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["status"] == "RUNNING"
    assert detail["runs"][0]["dpi"] == 300


def test_collect_uses_document_defaults_when_omitted(client):
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["conf"] == 0.35
    assert detail["runs"][0]["dpi"] == 200


def test_hook_finishes_run_and_restarts_fiftyone(client, monkeypatch):
    called = {}
    monkeypatch.setattr(runs_api.fiftyone_ctl, "restart",
                        lambda: called.setdefault("restart", True) or
                        {"ok": True, "orphans_killed": 0, "detail": "OK"})
    doc = _doc(client)
    ui_run_id = client.post(f"/api/sources/{doc}/collect", json={}).json()["data"]["ui_run_id"]

    r = client.post("/api/hooks/run-finished",
                    headers={"X-Hook-Token": "drheri-dev"},
                    json={"ui_run_id": ui_run_id, "dagster_run_id": "dagster-run-1",
                          "status": "SUCCESS", "extracted": 9, "error": None})
    assert r.json()["ok"] is True
    assert called["restart"] is True
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["status"] == "SUCCESS"
    assert detail["runs"][0]["extracted"] == 9


def test_hook_rejects_bad_token(client):
    r = client.post("/api/hooks/run-finished", headers={"X-Hook-Token": "wrong"},
                    json={"ui_run_id": 1, "status": "SUCCESS"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_hook_failure_does_not_restart_fiftyone(client, monkeypatch):
    called = {}
    monkeypatch.setattr(runs_api.fiftyone_ctl, "restart",
                        lambda: called.setdefault("restart", True))
    doc = _doc(client)
    ui_run_id = client.post(f"/api/sources/{doc}/collect", json={}).json()["data"]["ui_run_id"]
    client.post("/api/hooks/run-finished", headers={"X-Hook-Token": "drheri-dev"},
                json={"ui_run_id": ui_run_id, "status": "FAILURE",
                      "extracted": 0, "error": "PDF 다운로드 실패"})
    assert "restart" not in called
    detail = client.get(f"/api/sources/{doc}").json()["data"]
    assert detail["runs"][0]["status"] == "FAILURE"
    assert detail["runs"][0]["error"] == "PDF 다운로드 실패"


def test_latest_reconciles_running_run_from_dagster(client, monkeypatch):
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    monkeypatch.setattr(runs_api.dagster_client, "status", lambda rid: "SUCCESS")

    body = client.get(f"/api/sources/{doc}/runs/latest").json()["data"]
    assert body["status"] == "SUCCESS"
    with conn.session() as cx:
        assert queries.running_runs(cx) == []


def test_latest_marks_timeout_after_stall_limit(client, monkeypatch):
    """훅을 놓치고 Dagster 도 끝났다고 말하지 않는 런은 30분 뒤 TIMEOUT 처리한다(스펙 §13)."""
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    monkeypatch.setattr(runs_api.dagster_client, "status", lambda rid: "STARTED")
    with conn.session() as cx:
        cx.execute("UPDATE run SET started_at='2000-01-01T00:00:00+00:00' WHERE document_id=?",
                   (doc,))

    body = client.get(f"/api/sources/{doc}/runs/latest").json()["data"]
    assert body["status"] == "TIMEOUT"


def test_latest_keeps_running_before_stall_limit(client, monkeypatch):
    doc = _doc(client)
    client.post(f"/api/sources/{doc}/collect", json={})
    monkeypatch.setattr(runs_api.dagster_client, "status", lambda rid: "STARTED")

    body = client.get(f"/api/sources/{doc}/runs/latest").json()["data"]
    assert body["status"] == "RUNNING"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_api_runs.py -v`
Expected: FAIL — `ImportError: cannot import name 'runs' from 'drheri_pipeline.ui.api'`

- [ ] **Step 3: Dagster 클라이언트에 식별자 전달 추가**

`drheri_pipeline/ui/dagster_client.py` 의 `submit` 함수를 아래로 교체한다 (나머지는 그대로).

```python
def submit(*, pdf_url: str, brand: str, series: str, conf: float, dpi: int,
           pages: str, document_id: int, ui_run_id: int) -> str:
    """카탈로그 수집 잡 실행 → dagster run_id 반환.

    document_id/ui_run_id 를 함께 넘겨야 수집 결과가 어느 문서·어느 런의 것인지 DB 에 연결된다.
    """
    run_config = {
        "ops": {
            "catalog_pdf_images": {
                "config": {
                    "pdf_url": pdf_url,
                    "brand": brand or "Osstem",
                    "series": series or "_unknown",
                    "conf": float(conf),
                    "dpi": int(dpi),
                    "pages": pages or "",
                    "document_id": int(document_id),
                    "ui_run_id": int(ui_run_id),
                }
            }
        }
    }
    return _client().submit_job_execution(JOB, run_config=run_config)
```

- [ ] **Step 4: 실행·훅·SSE 라우트 구현**

`drheri_pipeline/ui/api/runs.py`:

```python
"""수집 실행 · 완료 훅 · SSE.

완료 감지는 Dagster run_status_sensor 가 /api/hooks/run-finished 를 때리는 푸시 방식이다.
훅을 놓친 경우(UI 재시작 등)에 대비해 /runs/latest 가 1회 정정한다 — 상시 폴링이 아니다.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

from drheri_pipeline.db import conn, queries, writes
from drheri_pipeline.services import fiftyone_ctl
from drheri_pipeline.ui import dagster_client
from drheri_pipeline.ui.envelope import ApiError, ok
from drheri_pipeline.ui.events import broadcaster

HOOK_TOKEN = os.getenv("HOOK_TOKEN", "drheri-dev")
DAGSTER_TERMINAL = {"SUCCESS", "FAILURE", "CANCELED"}
STALL_LIMIT = timedelta(minutes=30)


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        raise ApiError("invalid_request", "JSON 본문을 해석할 수 없습니다") from e
    return body if isinstance(body, dict) else {}


async def collect(request: Request):
    doc_id = request.path_params["doc_id"]
    body = await _json(request)

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

    try:
        dagster_run_id = await run_in_threadpool(
            lambda: dagster_client.submit(
                pdf_url=d["url"], brand=d["brand_raw"] or d["brand"],
                series=d["default_series"], conf=conf, dpi=dpi, pages=pages,
                document_id=doc_id, ui_run_id=run_id))
    except Exception as e:  # noqa: BLE001
        def _fail():
            with conn.session() as cx:
                writes.finish_run(cx, run_id, "FAILURE", 0, f"{e.__class__.__name__}: {e}")
        await run_in_threadpool(_fail)
        raise ApiError("dagster_submit_failed", f"수집 실행에 실패했습니다: {e}", status=502)

    def _attach():
        with conn.session() as cx:
            writes.attach_dagster_run(cx, run_id, dagster_run_id)

    await run_in_threadpool(_attach)
    return ok({"ui_run_id": run_id, "dagster_run_id": dagster_run_id})


def _stalled(started_at: str) -> bool:
    """훅도 못 받고 Dagster 도 종료를 알리지 않은 채 STALL_LIMIT 을 넘겼는지."""
    try:
        started = datetime.fromisoformat(started_at)
    except (TypeError, ValueError):
        return False
    return datetime.now(timezone.utc) - started > STALL_LIMIT


def _reconcile_latest(doc_id: int) -> dict | None:
    """최신 런 1건 조회. 진행 중이면 Dagster 에 한 번 물어 정정한다(상시 폴링 아님)."""
    with conn.session() as cx:
        row = cx.execute(
            """SELECT * FROM run WHERE document_id=? ORDER BY started_at DESC LIMIT 1""",
            (doc_id,)).fetchone()
        if row is None:
            return None
        run = dict(row)

    if run["status"] not in ("QUEUED", "RUNNING"):
        return run

    st = dagster_client.status(run["dagster_run_id"]) if run["dagster_run_id"] else None
    if st in DAGSTER_TERMINAL:
        final = st
    elif _stalled(run["started_at"]):
        final = "TIMEOUT"                       # 스펙 §13 — 30분 이상 멈춰 있으면 시간초과
    else:
        return run

    with conn.session() as cx:
        writes.finish_run(cx, run["id"], final, run["extracted"], run["error"])
    run["status"] = final
    return run


async def latest_run(request: Request):
    run = await run_in_threadpool(_reconcile_latest, request.path_params["doc_id"])
    if run is None:
        raise ApiError("not_found", "수집 이력이 없습니다", status=404)
    return ok(run)


async def run_log(request: Request):
    run_id = request.path_params["run_id"]

    def _get():
        with conn.session() as cx:
            row = cx.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    run = await run_in_threadpool(_get)
    if run is None:
        raise ApiError("not_found", "런을 찾을 수 없습니다", status=404)
    base = os.getenv("DAGSTER_URL", "http://58.229.105.3:3333")
    url = f"{base}/runs/{run['dagster_run_id']}" if run["dagster_run_id"] else None
    return ok({"run": run, "dagster_url": url})


async def hook_run_finished(request: Request):
    if request.headers.get("X-Hook-Token") != HOOK_TOKEN:
        raise ApiError("unauthorized", "훅 토큰이 올바르지 않습니다", status=401)
    body = await _json(request)
    ui_run_id = int(body.get("ui_run_id") or 0)
    status = (body.get("status") or "").upper()
    if not ui_run_id or status not in DAGSTER_TERMINAL:
        raise ApiError("invalid_request", "ui_run_id 와 status 가 필요합니다")

    extracted = int(body.get("extracted") or 0)
    error = body.get("error")

    def _finish():
        with conn.session() as cx:
            writes.finish_run(cx, ui_run_id, status, extracted, error)
            row = cx.execute("SELECT document_id FROM run WHERE id=?", (ui_run_id,)).fetchone()
            return row["document_id"] if row else None

    doc_id = await run_in_threadpool(_finish)

    restart = None
    if status == "SUCCESS":
        restart = await run_in_threadpool(fiftyone_ctl.restart)

    broadcaster.publish("run.finished", {
        "ui_run_id": ui_run_id, "document_id": doc_id, "status": status,
        "extracted": extracted, "error": error, "fiftyone": restart})
    return ok({"ui_run_id": ui_run_id, "fiftyone": restart})


async def events(request: Request):
    q = broadcaster.subscribe()
    return StreamingResponse(broadcaster.sse_stream(q), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


routes = [
    Route("/api/sources/{doc_id:int}/collect", collect, methods=["POST"]),
    Route("/api/sources/{doc_id:int}/runs/latest", latest_run, methods=["GET"]),
    Route("/api/runs/{run_id:int}/log", run_log, methods=["GET"]),
    Route("/api/hooks/run-finished", hook_run_finished, methods=["POST"]),
    Route("/api/events", events, methods=["GET"]),
]
```

- [ ] **Step 5: 앱에 라우트 등록**

`drheri_pipeline/ui/app.py` 에서 import 와 routes 를 다음으로 바꾼다.

```python
from drheri_pipeline.ui.api import runs, sources
```

```python
        routes=[*sources.routes, *runs.routes],
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_api_runs.py -v`
Expected: PASS (8 passed)

- [ ] **Step 7: 커밋**

```bash
git add drheri_pipeline/ui/dagster_client.py drheri_pipeline/ui/api/runs.py \
        drheri_pipeline/ui/app.py tests/test_api_runs.py
git commit -m "feat: 수집 실행 API 와 완료 훅, SSE 엔드포인트 추가"
```

---

### Task 12: Dagster 센서 — 완료 시 UI 훅 호출

`run_status_sensor` 는 Dagster 데몬이 RUN_SUCCESS/RUN_FAILURE 때 호출한다. 폴링이 아니다. (`dagster dev` 에 데몬이 포함되어 있다.)

**Files:**
- Create: `drheri_pipeline/sensors.py`
- Modify: `drheri_pipeline/definitions.py`
- Test: `tests/test_sensors.py`

**Interfaces:**
- Consumes: `httpx`, Dagster `RunStatusSensorContext`
- Produces:
  - `sensors.hook_payload(run_config: dict, status: str, error: str | None) -> dict | None` — UI 미경유 런이면 None
  - `sensors.post_hook(payload: dict) -> bool`
  - `sensors.ui_run_finished` — `run_status_sensor` 두 개 (`on_run_success`, `on_run_failure`)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_sensors.py`:

```python
from drheri_pipeline import sensors

CFG = {"ops": {"catalog_pdf_images": {"config": {
    "document_id": 3, "ui_run_id": 11, "pdf_url": "https://ex.com/a.pdf"}}}}


def test_hook_payload_extracts_identifiers():
    p = sensors.hook_payload(CFG, "SUCCESS", None)
    assert p == {"ui_run_id": 11, "document_id": 3, "status": "SUCCESS",
                 "extracted": 0, "error": None}


def test_hook_payload_none_when_not_from_ui():
    cfg = {"ops": {"catalog_pdf_images": {"config": {"document_id": 0, "ui_run_id": 0}}}}
    assert sensors.hook_payload(cfg, "SUCCESS", None) is None
    assert sensors.hook_payload({}, "SUCCESS", None) is None


def test_post_hook_sends_token_header(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, json=json, headers=headers)
        return Resp()

    monkeypatch.setattr(sensors.httpx, "post", fake_post)
    assert sensors.post_hook({"ui_run_id": 11, "status": "SUCCESS"}) is True
    assert sent["headers"]["X-Hook-Token"] == sensors.HOOK_TOKEN
    assert sent["url"].endswith("/api/hooks/run-finished")


def test_post_hook_returns_false_on_error(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(sensors.httpx, "post", boom)
    assert sensors.post_hook({"ui_run_id": 1}) is False
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_sensors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drheri_pipeline.sensors'`

- [ ] **Step 3: 구현**

`drheri_pipeline/sensors.py`:

```python
"""Dagster 런 상태 센서 → UI 완료 훅 POST.

데몬이 이벤트 기반으로 호출하므로 UI 쪽 폴링 루프가 필요 없다.
UI 를 거치지 않은 직접 실행(document_id=0)은 훅을 보내지 않는다.
"""
import os

import httpx
from dagster import DagsterRunStatus, RunStatusSensorContext, run_status_sensor

UI_BASE = os.getenv("UI_BASE_URL", "http://127.0.0.1:3000")
HOOK_TOKEN = os.getenv("HOOK_TOKEN", "drheri-dev")
HOOK_URL = f"{UI_BASE}/api/hooks/run-finished"
OPS = ("catalog_pdf_images", "site_xray_images")


def hook_payload(run_config: dict, status: str, error):
    """런 설정에서 UI 식별자를 뽑아 훅 본문을 만든다. UI 미경유면 None."""
    ops = (run_config or {}).get("ops") or {}
    for name in OPS:
        cfg = (ops.get(name) or {}).get("config") or {}
        ui_run_id = int(cfg.get("ui_run_id") or 0)
        if ui_run_id:
            return {"ui_run_id": ui_run_id,
                    "document_id": int(cfg.get("document_id") or 0),
                    "status": status, "extracted": 0, "error": error}
    return None


def post_hook(payload: dict) -> bool:
    try:
        r = httpx.post(HOOK_URL, json=payload,
                       headers={"X-Hook-Token": HOOK_TOKEN}, timeout=120)
        return 200 <= r.status_code < 300
    except Exception:  # noqa: BLE001
        return False


def _notify(context: RunStatusSensorContext, status: str, error) -> None:
    payload = hook_payload(context.dagster_run.run_config, status, error)
    if payload is None:
        context.log.info("UI 미경유 런 — 훅 생략")
        return
    ok = post_hook(payload)
    context.log.info(f"UI 훅 전송 {'성공' if ok else '실패'} — {payload}")


@run_status_sensor(run_status=DagsterRunStatus.SUCCESS)
def on_run_success(context: RunStatusSensorContext):
    _notify(context, "SUCCESS", None)


@run_status_sensor(run_status=DagsterRunStatus.FAILURE)
def on_run_failure(context: RunStatusSensorContext):
    err = None
    if context.failure_event and context.failure_event.message:
        err = context.failure_event.message[:500]
    _notify(context, "FAILURE", err)
```

`drheri_pipeline/definitions.py` 를 아래로 교체한다.

```python
"""Dagster 진입점 (pyproject [tool.dagster] module_name)."""
from dagster import Definitions

from . import assets, sensors

defs = Definitions(
    assets=[assets.site_xray_images, assets.catalog_pdf_images],
    jobs=[assets.ingest_site_xray_job, assets.ingest_catalog_pdf_job],
    sensors=[sensors.on_run_success, sensors.on_run_failure],
)
```

`extracted` 는 센서가 알 수 없어 0 으로 보낸다. 실제 추출 수는 Task 5 에서 자산이 이미 DB 에 기록했고, 퍼널은 `image_origin` 을 세므로 정확하다. `run.extracted` 는 참고값이다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_sensors.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Dagster 정의 로드 확인**

Run: `.venv/bin/python -c "from drheri_pipeline.definitions import defs; print([s.name for s in defs.sensors])"`
Expected: `['on_run_success', 'on_run_failure']`

- [ ] **Step 6: 커밋**

```bash
git add drheri_pipeline/sensors.py drheri_pipeline/definitions.py tests/test_sensors.py
git commit -m "feat: Dagster 런 상태 센서로 완료를 UI 에 푸시"
```

---

### Task 13: 운영 API — sync / export / overview / settings / health / restart

**Files:**
- Create: `drheri_pipeline/ui/api/ops.py`
- Modify: `drheri_pipeline/ui/app.py`
- Test: `tests/test_api_ops.py`

**Interfaces:**
- Consumes: `services.sync.run_sync`, `services.export.export_all/class_distribution`, `services.fiftyone_ctl`, `db.queries.overview`, `events.broadcaster`
- Produces:
  - `ops.routes` — `POST /api/sync`, `GET /api/overview`, `GET /api/export/summary`,
    `POST /api/export`, `GET /api/settings`, `POST /api/settings`,
    `POST /api/fiftyone/restart`, `GET /api/health`
  - `ops.SETTINGS_KEYS` — 설정 화면에 노출할 환경변수 키 목록
  - 동기화 중복 실행 방지: 진행 중이면 409 `sync_in_progress`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api_ops.py`:

```python
import pytest
from starlette.testclient import TestClient

from drheri_pipeline.ui import app as ui_app
from drheri_pipeline.ui.api import ops as ops_api


@pytest.fixture()
def client(data_root):
    return TestClient(ui_app.create_app())


def test_sync_returns_counts_and_publishes_event(client, monkeypatch):
    monkeypatch.setattr(ops_api.sync, "run_sync",
                        lambda: {"kept": 3, "rejected": 1, "promoted": 2, "note": "샘플 4건 확인"})
    published = []
    monkeypatch.setattr(ops_api.broadcaster, "publish",
                        lambda e, p: published.append((e, p)))
    body = client.post("/api/sync").json()
    assert body["data"]["promoted"] == 2
    assert published[0][0] == "sync.finished"


def test_sync_rejects_concurrent_run(client, monkeypatch):
    monkeypatch.setattr(ops_api, "_sync_running", True)
    r = client.post("/api/sync")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "sync_in_progress"


def test_overview_returns_funnel_and_recent_runs(client):
    data = client.get("/api/overview").json()["data"]
    assert data["funnel"]["extracted"] == 0
    assert data["recent_runs"] == []
    assert "services" in data


def test_export_writes_files(client):
    data = client.post("/api/export").json()["data"]
    assert data["rows"] == 0
    assert data["labels_tsv"].endswith("labels.tsv")

    summary = client.get("/api/export/summary").json()["data"]
    assert summary["total"] == 0


def test_settings_roundtrip(client):
    before = client.get("/api/settings").json()["data"]
    assert "DEFAULT_CONF" in before
    client.post("/api/settings", json={"DEFAULT_CONF": "0.5"})
    after = client.get("/api/settings").json()["data"]
    assert after["DEFAULT_CONF"] == "0.5"


def test_fiftyone_restart_route(client, monkeypatch):
    monkeypatch.setattr(ops_api.fiftyone_ctl, "restart",
                        lambda: {"ok": True, "orphans_killed": 2, "detail": "OK"})
    body = client.post("/api/fiftyone/restart").json()
    assert body["data"]["orphans_killed"] == 2


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["data"]["db"] is True
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_api_ops.py -v`
Expected: FAIL — `ImportError: cannot import name 'ops' from 'drheri_pipeline.ui.api'`

- [ ] **Step 3: 구현**

`drheri_pipeline/ui/api/ops.py`:

```python
"""운영 API — 검수 동기화, 내보내기, 현황, 설정, 헬스체크, FiftyOne 재기동.

설정은 프로세스 환경변수에 얹는 얇은 계층이다. 값은 data/settings.json 에 저장하고
기동 시 환경변수로 로드한다(별도 설정 서버를 두지 않는다).
"""
from __future__ import annotations

import json
import os

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.routing import Route

from drheri_pipeline import storage
from drheri_pipeline.db import conn, queries
from drheri_pipeline.services import export, fiftyone_ctl, sync
from drheri_pipeline.ui.envelope import ApiError, ok
from drheri_pipeline.ui.events import broadcaster

SETTINGS_KEYS = ("DEFAULT_CONF", "DEFAULT_DPI", "DATA_ROOT", "DAGSTER_URL",
                 "FIFTYONE_URL", "FIFTYONE_SERVICE")
DEFAULTS = {"DEFAULT_CONF": "0.35", "DEFAULT_DPI": "200",
            "DAGSTER_URL": "http://58.229.105.3:3333",
            "FIFTYONE_URL": "http://58.229.105.3:5151",
            "FIFTYONE_SERVICE": "drheri-fiftyone"}

_sync_running = False


def _settings_path():
    return storage.DATA_ROOT / "settings.json"


def _read_settings() -> dict:
    stored = {}
    p = _settings_path()
    if p.exists():
        stored = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for k in SETTINGS_KEYS:
        out[k] = stored.get(k) or os.getenv(k) or DEFAULTS.get(k, "")
    out["DATA_ROOT"] = str(storage.DATA_ROOT)
    return out


async def get_settings(request: Request):
    return ok(await run_in_threadpool(_read_settings))


async def post_settings(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise ApiError("invalid_request", "JSON 객체가 필요합니다")

    def _write():
        cur = _read_settings()
        cur.update({k: str(v) for k, v in body.items() if k in SETTINGS_KEYS})
        cur.pop("DATA_ROOT", None)                # 경로는 환경변수로만 바꾼다
        _settings_path().write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        for k, v in cur.items():
            os.environ[k] = v
        return _read_settings()

    return ok(await run_in_threadpool(_write))


async def post_sync(request: Request):
    global _sync_running
    if _sync_running:
        raise ApiError("sync_in_progress", "검수결과 반영이 이미 진행 중입니다", status=409)
    _sync_running = True
    try:
        result = await run_in_threadpool(sync.run_sync)
    finally:
        _sync_running = False
    broadcaster.publish("sync.finished", result)
    return ok(result)


async def get_overview(request: Request):
    def _load():
        with conn.session() as cx:
            data = queries.overview(cx)
        data["services"] = {"fiftyone": fiftyone_ctl.health()}
        return data

    return ok(await run_in_threadpool(_load))


async def post_export(request: Request):
    result = await run_in_threadpool(export.export_all)
    broadcaster.publish("export.finished", result)
    return ok(result)


async def get_export_summary(request: Request):
    def _load():
        with conn.session() as cx:
            return export.class_distribution(cx)

    return ok(await run_in_threadpool(_load))


async def post_restart(request: Request):
    return ok(await run_in_threadpool(fiftyone_ctl.restart))


async def get_health(request: Request):
    def _check():
        try:
            with conn.session() as cx:
                cx.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    return ok({"db": await run_in_threadpool(_check), "sync_running": _sync_running})


routes = [
    Route("/api/sync", post_sync, methods=["POST"]),
    Route("/api/overview", get_overview, methods=["GET"]),
    Route("/api/export", post_export, methods=["POST"]),
    Route("/api/export/summary", get_export_summary, methods=["GET"]),
    Route("/api/settings", get_settings, methods=["GET"]),
    Route("/api/settings", post_settings, methods=["POST"]),
    Route("/api/fiftyone/restart", post_restart, methods=["POST"]),
    Route("/api/health", get_health, methods=["GET"]),
]
```

`drheri_pipeline/ui/app.py` 의 import 와 routes 를 갱신한다.

```python
from drheri_pipeline.ui.api import ops, runs, sources
```

```python
        routes=[*sources.routes, *runs.routes, *ops.routes],
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_api_ops.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 전체 테스트 실행**

Run: `.venv/bin/python -m pytest tests -v`
Expected: PASS (59 passed)

- [ ] **Step 6: 커밋**

```bash
git add drheri_pipeline/ui/api/ops.py drheri_pipeline/ui/app.py tests/test_api_ops.py
git commit -m "feat: 운영 API 추가 (동기화·내보내기·현황·설정·헬스체크·재기동)"
```

---

### Task 14: 프론트엔드 기반 — Vite + Svelte 5, API 래퍼, 스토어, 라우터, 디자인 토큰

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.js`
- Create: `web/index.html`
- Create: `web/src/main.js`
- Create: `web/src/app.css`
- Create: `web/src/lib/api.js`
- Create: `web/src/lib/format.js`
- Create: `web/src/lib/router.svelte.js`
- Create: `web/src/lib/stores.svelte.js`
- Create: `web/src/lib/events.js`
- Create: `web/src/components/FunnelBar.svelte`
- Test: `web/src/lib/api.test.js`
- Test: `web/src/lib/format.test.js`

**Interfaces:**
- Produces:
  - `api.get(path, params?) -> Promise<any>` / `api.post(path, body?) -> Promise<any>` — 봉투를 벗겨 `data` 를 반환하고, `ok:false` 면 `ApiError` 를 던진다
  - `ApiError` — `{code, message, status}` 필드
  - `format.funnelSegments(funnel) -> [{key, label, count, color, pct}]`
  - `format.dateTime(iso) -> string` — `2026-07-20 14:02` (Asia/Seoul)
  - `router.route` — `$state` 객체 `{name, params}`; `navigate(hash)`
  - `stores.sources`, `stores.toasts` — `$state` 컨테이너
  - `events.connect()` — SSE 연결, 이벤트 수신 시 스토어 갱신

- [ ] **Step 1: 프로젝트 생성**

```bash
cd /c/dev/Dr.HERi/data-pipeline
mkdir -p web/src/lib web/src/components web/src/routes
```

`web/package.json`:

```json
{
  "name": "drheri-ui-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run"
  },
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^5.0.0",
    "svelte": "^5.0.0",
    "vite": "^6.0.0",
    "vitest": "^2.0.0"
  }
}
```

`web/vite.config.js`:

```js
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  build: { outDir: 'dist', emptyOutDir: true },
  // 개발 중에는 API 를 3000번 UI 서버로 프록시한다.
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:3000' } },
});
```

`web/index.html`:

```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Dr.HERi 데이터 파이프라인</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

```bash
cd web && npm install
```

- [ ] **Step 2: 실패하는 테스트 작성**

`web/src/lib/api.test.js`:

```js
import { afterEach, expect, test, vi } from 'vitest';
import { ApiError, get, post } from './api.js';

afterEach(() => vi.restoreAllMocks());

function mockFetch(body, status = 200) {
  globalThis.fetch = vi.fn(async () => ({
    status,
    json: async () => body,
  }));
}

test('get 은 봉투를 벗겨 data 를 반환한다', async () => {
  mockFetch({ ok: true, data: { id: 1 }, error: null });
  expect(await get('/api/sources')).toEqual({ id: 1 });
});

test('get 은 쿼리 파라미터를 붙인다', async () => {
  mockFetch({ ok: true, data: null, error: null });
  await get('/api/sources/check', { url: 'https://ex.com/a.pdf' });
  expect(globalThis.fetch.mock.calls[0][0]).toBe(
    '/api/sources/check?url=https%3A%2F%2Fex.com%2Fa.pdf',
  );
});

test('ok:false 면 ApiError 를 던진다', async () => {
  mockFetch({ ok: false, data: null, error: { code: 'duplicate_url', message: '이미 등록됨' } }, 409);
  await expect(post('/api/sources', {})).rejects.toMatchObject({
    code: 'duplicate_url',
    message: '이미 등록됨',
    status: 409,
  });
});

test('post 는 JSON 본문을 보낸다', async () => {
  mockFetch({ ok: true, data: { id: 2 }, error: null });
  await post('/api/sources', { url: 'x' });
  const init = globalThis.fetch.mock.calls[0][1];
  expect(init.method).toBe('POST');
  expect(JSON.parse(init.body)).toEqual({ url: 'x' });
});

test('ApiError 는 Error 를 상속한다', () => {
  expect(new ApiError('c', 'm', 400)).toBeInstanceOf(Error);
});
```

`web/src/lib/format.test.js`:

```js
import { expect, test } from 'vitest';
import { dateTime, funnelSegments } from './format.js';

const FUNNEL = { extracted: 100, training: 30, rejected: 10, pending: 60 };

test('funnelSegments 는 학습·버림·대기 순으로 3구간을 만든다', () => {
  const segs = funnelSegments(FUNNEL);
  expect(segs.map((s) => s.key)).toEqual(['training', 'rejected', 'pending']);
  expect(segs.map((s) => s.count)).toEqual([30, 10, 60]);
});

test('funnelSegments 의 비율 합은 100 이다', () => {
  const total = funnelSegments(FUNNEL).reduce((a, s) => a + s.pct, 0);
  expect(Math.round(total)).toBe(100);
});

test('추출이 0이면 모든 구간이 0% 다', () => {
  const segs = funnelSegments({ extracted: 0, training: 0, rejected: 0, pending: 0 });
  expect(segs.every((s) => s.pct === 0)).toBe(true);
});

test('dateTime 은 서울 시간으로 분까지 표시한다', () => {
  expect(dateTime('2026-07-20T05:02:00+00:00')).toBe('2026-07-20 14:02');
});

test('dateTime 은 빈 값에 대해 대시를 반환한다', () => {
  expect(dateTime(null)).toBe('—');
});
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd web && npm test`
Expected: FAIL — `Failed to resolve import "./api.js"`

- [ ] **Step 4: 구현**

`web/src/lib/api.js`:

```js
// API 래퍼 — 서버 봉투 {ok,data,error} 를 벗겨 data 만 돌려준다.
export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

async function request(path, init) {
  const res = await fetch(path, init);
  const body = await res.json();
  if (!body.ok) {
    const e = body.error || {};
    throw new ApiError(e.code || 'unknown', e.message || '알 수 없는 오류', res.status);
  }
  return body.data;
}

export function get(path, params) {
  const qs = params ? `?${new URLSearchParams(params)}` : '';
  return request(`${path}${qs}`, { method: 'GET' });
}

export function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });
}
```

`web/src/lib/format.js`:

```js
// 퍼널 표시와 일시 포맷.
export const FUNNEL_COLORS = {
  training: '#059669',
  rejected: '#dc2626',
  pending: '#e5e7eb',
};

const LABELS = { training: '학습', rejected: '버림', pending: '대기' };

export function funnelSegments(funnel) {
  const total = funnel?.extracted || 0;
  return ['training', 'rejected', 'pending'].map((key) => {
    const count = funnel?.[key] || 0;
    return {
      key,
      label: LABELS[key],
      count,
      color: FUNNEL_COLORS[key],
      pct: total ? (count / total) * 100 : 0,
    };
  });
}

const DT = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hour12: false,
});

export function dateTime(iso) {
  if (!iso) return '—';
  const parts = Object.fromEntries(DT.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

export function num(n) {
  return (n ?? 0).toLocaleString('ko-KR');
}
```

`web/src/lib/router.svelte.js`:

```js
// 의존성 없는 해시 라우터. #/sources, #/sources/12, #/overview, #/export, #/settings
const ROUTES = [
  [/^#\/sources\/(\d+)$/, (m) => ({ name: 'sourceDetail', params: { id: Number(m[1]) } })],
  [/^#\/sources$/, () => ({ name: 'sources', params: {} })],
  [/^#\/overview$/, () => ({ name: 'overview', params: {} })],
  [/^#\/export$/, () => ({ name: 'export', params: {} })],
  [/^#\/settings$/, () => ({ name: 'settings', params: {} })],
];

function parse(hash) {
  for (const [re, make] of ROUTES) {
    const m = hash.match(re);
    if (m) return make(m);
  }
  return { name: 'sources', params: {} };
}

export const route = $state(parse(location.hash || '#/sources'));

export function navigate(hash) {
  location.hash = hash;
}

window.addEventListener('hashchange', () => {
  const next = parse(location.hash);
  route.name = next.name;
  route.params = next.params;
});
```

`web/src/lib/stores.svelte.js`:

```js
import { get } from './api.js';

export const sources = $state({ tree: [], loading: false, error: null });
export const toasts = $state({ items: [] });

let toastSeq = 0;

export function toast(message, kind = 'info') {
  const id = ++toastSeq;
  toasts.items = [...toasts.items, { id, message, kind }];
  setTimeout(() => {
    toasts.items = toasts.items.filter((t) => t.id !== id);
  }, 5000);
}

export async function loadSources() {
  sources.loading = true;
  sources.error = null;
  try {
    sources.tree = await get('/api/sources');
  } catch (e) {
    sources.error = e.message;
    toast(e.message, 'error');
  } finally {
    sources.loading = false;
  }
}
```

`web/src/lib/events.js`:

```js
// SSE 구독 — 수집/동기화 완료 시 화면을 갱신한다. 폴링하지 않는다.
import { loadSources, toast } from './stores.svelte.js';

export function connect() {
  const es = new EventSource('/api/events');

  es.addEventListener('run.finished', (e) => {
    const p = JSON.parse(e.data);
    if (p.status === 'SUCCESS') {
      toast(`수집 완료 — ${p.extracted}장`, 'success');
    } else {
      toast(`수집 실패 — ${p.error || p.status}`, 'error');
    }
    if (p.fiftyone && !p.fiftyone.ok) {
      toast(`FiftyOne 재기동 실패: ${p.fiftyone.detail}`, 'error');
    }
    loadSources();
  });

  es.addEventListener('sync.finished', (e) => {
    const p = JSON.parse(e.data);
    toast(`검수결과 반영 — 학습 승급 ${p.promoted} · 버림 ${p.rejected}`, 'success');
    loadSources();
  });

  es.addEventListener('export.finished', (e) => {
    toast(`내보내기 완료 — ${JSON.parse(e.data).rows}행`, 'success');
  });

  return es;
}
```

`web/src/app.css` — 디자인 토큰 (미니멀 실무형):

```css
:root {
  --bg: #ffffff;
  --border: #e5e7eb;
  --text: #111827;
  --muted: #6b7280;
  --accent: #2563eb;
  --training: #059669;
  --rejected: #dc2626;
  --pending: #e5e7eb;
  --row-h: 36px;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: var(--font);
  font-size: 13px;
  color: var(--text);
  background: var(--bg);
}

.label { font-size: 11px; color: var(--muted); }
.num { font-variant-numeric: tabular-nums; }

button {
  font: inherit;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
button:disabled { opacity: 0.5; cursor: default; }

input, select, textarea {
  font: inherit;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  width: 100%;
}

table { width: 100%; border-collapse: collapse; }
th, td { height: var(--row-h); text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 11px; color: var(--muted); font-weight: 500; }
```

`web/src/components/FunnelBar.svelte` — 목록·상세·현황이 공유하는 유일한 퍼널 컴포넌트:

```svelte
<script>
  import { funnelSegments, num } from '../lib/format.js';

  let { funnel, showNumbers = true, height = 8 } = $props();
  let segments = $derived(funnelSegments(funnel));
  let tooltip = $derived(
    `미검수 ${funnel?.unreviewed ?? 0} · 라벨 미완 ${funnel?.label_incomplete ?? 0}`,
  );
</script>

<div class="bar" style="height:{height}px" title={tooltip}>
  {#each segments as s (s.key)}
    <span style="width:{s.pct}%; background:{s.color}"></span>
  {/each}
</div>

{#if showNumbers}
  <div class="nums label">
    <span>추출 <b class="num">{num(funnel?.extracted)}</b></span>
    {#each segments as s (s.key)}
      <span style="color:{s.key === 'pending' ? 'var(--muted)' : s.color}">
        {s.label} <b class="num">{num(s.count)}</b>
      </span>
    {/each}
  </div>
{/if}

<style>
  .bar {
    display: flex;
    width: 100%;
    background: var(--pending);
    border-radius: 4px;
    overflow: hidden;
  }
  .bar span { display: block; }
  .nums { display: flex; gap: 10px; margin-top: 4px; }
</style>
```

`web/src/main.js`:

```js
import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';

export default mount(App, { target: document.getElementById('app') });
```

`App.svelte` 는 Task 15 에서 만든다. 이 태스크의 테스트는 `lib/` 만 검증한다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd web && npm test`
Expected: PASS (10 passed — api 5, format 5)

- [ ] **Step 6: 커밋**

```bash
git add web/package.json web/package-lock.json web/vite.config.js web/index.html web/src
git commit -m "feat: Svelte 5 프론트엔드 기반 추가 (API 래퍼·스토어·라우터·퍼널 컴포넌트)"
```

---

### Task 15: 셸 + 소스 화면 (브랜드 › 문서 트리, 등록 모달)

**Files:**
- Create: `web/src/App.svelte`
- Create: `web/src/components/Toast.svelte`
- Create: `web/src/components/Modal.svelte`
- Create: `web/src/components/BrandGroup.svelte`
- Create: `web/src/routes/Sources.svelte`
- Create: `web/src/routes/NewSource.svelte`

**Interfaces:**
- Consumes: `lib/api`, `lib/stores.svelte.js`, `lib/router.svelte.js`, `lib/events.js`, `components/FunnelBar.svelte`
- Produces:
  - `App.svelte` — 상단바(로고 · Dagster/FiftyOne 링크 · `검수결과 반영`) + 사이드바 4메뉴 + 라우트 아웃렛
  - `NewSource.svelte` — props `{ onclose }`. URL 입력 blur 시 `/api/sources/check` 로 중복 확인
  - `BrandGroup.svelte` — props `{ group }`. 접이식 브랜드 헤더 + 문서 행

- [ ] **Step 1: Toast / Modal 작성**

`web/src/components/Toast.svelte`:

```svelte
<script>
  import { toasts } from '../lib/stores.svelte.js';
</script>

<div class="wrap">
  {#each toasts.items as t (t.id)}
    <div class="toast {t.kind}">{t.message}</div>
  {/each}
</div>

<style>
  .wrap { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 6px; z-index: 50; }
  .toast { padding: 8px 12px; border-radius: 4px; border: 1px solid var(--border); background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  .toast.success { border-left: 3px solid var(--training); }
  .toast.error { border-left: 3px solid var(--rejected); }
  .toast.info { border-left: 3px solid var(--accent); }
</style>
```

`web/src/components/Modal.svelte`:

```svelte
<script>
  let { title, onclose, children } = $props();
</script>

<div class="backdrop" onclick={onclose} role="presentation">
  <div class="panel" onclick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
    <header>
      <b>{title}</b>
      <button onclick={onclose} aria-label="닫기">✕</button>
    </header>
    <div class="body">{@render children()}</div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(17,24,39,.35); display: flex; align-items: center; justify-content: center; z-index: 40; }
  .panel { background: #fff; border-radius: 6px; width: 520px; max-width: 92vw; max-height: 88vh; overflow: auto; }
  header { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; border-bottom: 1px solid var(--border); }
  header button { border: none; background: none; padding: 2px 6px; }
  .body { padding: 14px; }
</style>
```

- [ ] **Step 2: 등록 폼 작성 — 중복 URL 즉시 확인**

`web/src/routes/NewSource.svelte`:

```svelte
<script>
  import { post, get } from '../lib/api.js';
  import Modal from '../components/Modal.svelte';
  import { loadSources, toast } from '../lib/stores.svelte.js';
  import { navigate } from '../lib/router.svelte.js';

  let { onclose } = $props();

  let form = $state({ url: '', name: '', brand: 'Osstem', series: '',
                      conf: 0.35, dpi: 200, pages: '', memo: '' });
  let duplicate = $state(null);
  let saving = $state(false);

  async function checkUrl() {
    duplicate = null;
    if (!form.url.trim()) return;
    try {
      const r = await get('/api/sources/check', { url: form.url });
      if (r.exists) duplicate = r.document;
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function save(andCollect) {
    saving = true;
    try {
      const { id } = await post('/api/sources', {
        url: form.url, name: form.name, brand: form.brand,
        series: form.series || '_unknown', conf: Number(form.conf),
        dpi: Number(form.dpi), pages: form.pages, memo: form.memo,
      });
      await loadSources();
      onclose();
      if (andCollect) {
        await post(`/api/sources/${id}/collect`, {});
        toast('수집을 시작했습니다', 'info');
      }
      navigate(`#/sources/${id}`);
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      saving = false;
    }
  }
</script>

<Modal title="새 카탈로그 등록" {onclose}>
  {#snippet children()}
    <div class="label">카탈로그 PDF 주소</div>
    <input bind:value={form.url} onblur={checkUrl} placeholder="https://…/catalog.pdf" />
    {#if duplicate}
      <div class="warn">
        ⚠️ 이미 등록된 URL 입니다 —
        <a href="#/sources/{duplicate.id}" onclick={onclose}>{duplicate.name} 보기 →</a>
      </div>
    {/if}

    <div class="label">이름 <span>(비우면 주소의 파일명)</span></div>
    <input bind:value={form.name} />

    <div class="row">
      <div><div class="label">브랜드</div><input bind:value={form.brand} /></div>
      <div><div class="label">기본 시리즈</div><input bind:value={form.series} placeholder="비우면 미지정" /></div>
    </div>

    <div class="label">기본 수집 설정</div>
    <div class="row">
      <input bind:value={form.conf} placeholder="conf" />
      <input bind:value={form.dpi} placeholder="dpi" />
      <input bind:value={form.pages} placeholder="페이지 (비우면 전체)" />
    </div>

    <div class="label">메모</div>
    <input bind:value={form.memo} placeholder="예: TS·GS 혼재. 10~16p 가 상세" />

    <div class="actions">
      <button class="primary" disabled={saving || !form.url.trim() || !!duplicate}
              onclick={() => save(false)}>등록</button>
      <button disabled={saving || !form.url.trim() || !!duplicate}
              onclick={() => save(true)}>등록하고 바로 수집</button>
    </div>
  {/snippet}
</Modal>

<style>
  .label { margin: 10px 0 4px; }
  .row { display: flex; gap: 6px; }
  .row > * { flex: 1; }
  .warn { margin-top: 6px; padding: 6px 8px; font-size: 11px; border-radius: 4px;
          background: #fffbeb; border: 1px solid #fde68a; color: #b45309; }
  .actions { display: flex; gap: 6px; margin-top: 14px; }
</style>
```

- [ ] **Step 3: 브랜드 그룹과 소스 화면 작성**

`web/src/components/BrandGroup.svelte`:

```svelte
<script>
  import FunnelBar from './FunnelBar.svelte';
  import { dateTime, num } from '../lib/format.js';

  let { group } = $props();
  let open = $state(true);
</script>

<section>
  <button class="head" onclick={() => (open = !open)}>
    <span class="caret">{open ? '▾' : '▸'}</span>
    <b>{group.brand}</b>
    <span class="label">문서 {group.documents.length}</span>
    <span class="bar"><FunnelBar funnel={group.funnel} showNumbers={false} height={6} /></span>
    <span class="label num">
      추출 {num(group.funnel.extracted)} · 학습 {num(group.funnel.training)}
      · 버림 {num(group.funnel.rejected)} · 대기 {num(group.funnel.pending)}
    </span>
  </button>

  {#if open}
    <table>
      <thead>
        <tr><th>문서</th><th style="width:180px">퍼널</th><th style="width:130px">마지막 수집</th></tr>
      </thead>
      <tbody>
        {#each group.documents as d (d.id)}
          <tr>
            <td><a href="#/sources/{d.id}">{d.name}</a> <span class="label">{d.url}</span></td>
            <td>
              <FunnelBar funnel={d.funnel} showNumbers={false} height={6} />
              <span class="label num">
                {num(d.funnel.extracted)} / {num(d.funnel.training)} /
                {num(d.funnel.rejected)} / {num(d.funnel.pending)}
              </span>
            </td>
            <td class="label">{dateTime(d.last_run_at)} {d.last_run_status ?? ''}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</section>

<style>
  section { margin-bottom: 18px; }
  .head { display: flex; align-items: center; gap: 8px; width: 100%; border: none;
          background: none; padding: 6px 0; text-align: left; }
  .caret { color: var(--muted); }
  .bar { flex: 0 0 160px; }
  td a { color: var(--text); }
  td .label { margin-left: 6px; }
</style>
```

`web/src/routes/Sources.svelte`:

```svelte
<script>
  import BrandGroup from '../components/BrandGroup.svelte';
  import NewSource from './NewSource.svelte';
  import { loadSources, sources } from '../lib/stores.svelte.js';

  let showNew = $state(false);
  $effect(() => { loadSources(); });
</script>

<header class="page">
  <h2>소스</h2>
  <button class="primary" onclick={() => (showNew = true)}>+ 새 카탈로그 등록</button>
</header>

{#if sources.loading}
  <p class="label">불러오는 중…</p>
{:else if sources.tree.length === 0}
  <p class="label">등록된 소스가 없습니다. 카탈로그 PDF 주소를 등록해 시작하세요.</p>
{:else}
  {#each sources.tree as g (g.brand_id)}
    <BrandGroup group={g} />
  {/each}
{/if}

{#if showNew}
  <NewSource onclose={() => (showNew = false)} />
{/if}

<style>
  .page { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  h2 { font-size: 15px; margin: 0; }
</style>
```

- [ ] **Step 4: 앱 셸 작성**

`web/src/App.svelte`:

```svelte
<script>
  import { onMount } from 'svelte';
  import { post } from './lib/api.js';
  import { connect } from './lib/events.js';
  import { route } from './lib/router.svelte.js';
  import { toast } from './lib/stores.svelte.js';
  import Toast from './components/Toast.svelte';
  import Sources from './routes/Sources.svelte';
  import SourceDetail from './routes/SourceDetail.svelte';
  import Overview from './routes/Overview.svelte';
  import Export from './routes/Export.svelte';
  import Settings from './routes/Settings.svelte';

  const MENU = [
    ['sources', '#/sources', '소스'],
    ['overview', '#/overview', '현황'],
    ['export', '#/export', '학습데이터'],
    ['settings', '#/settings', '설정'],
  ];

  let syncing = $state(false);

  onMount(() => {
    const es = connect();
    return () => es.close();
  });

  async function sync() {
    syncing = true;
    try {
      await post('/api/sync');            // 결과 토스트는 SSE 가 띄운다
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      syncing = false;
    }
  }
</script>

<nav class="top">
  <b>Dr.HERi 데이터 파이프라인</b>
  <div class="right">
    <a href="http://58.229.105.3:3333" target="_blank" rel="noreferrer">Dagster ↗</a>
    <a href="http://58.229.105.3:5151" target="_blank" rel="noreferrer">FiftyOne ↗</a>
    <button class="primary" onclick={sync} disabled={syncing}>
      {syncing ? '반영 중…' : '검수결과 반영'}
    </button>
  </div>
</nav>

<div class="body">
  <aside>
    {#each MENU as [name, href, text] (name)}
      <a {href} class:active={route.name === name || (name === 'sources' && route.name === 'sourceDetail')}>{text}</a>
    {/each}
  </aside>

  <main>
    {#if route.name === 'sources'}
      <Sources />
    {:else if route.name === 'sourceDetail'}
      <SourceDetail id={route.params.id} />
    {:else if route.name === 'overview'}
      <Overview />
    {:else if route.name === 'export'}
      <Export />
    {:else if route.name === 'settings'}
      <Settings />
    {/if}
  </main>
</div>

<Toast />

<style>
  .top { display: flex; justify-content: space-between; align-items: center;
         padding: 10px 16px; border-bottom: 1px solid var(--border); }
  .right { display: flex; align-items: center; gap: 12px; }
  .right a { color: var(--muted); text-decoration: none; font-size: 12px; }
  .body { display: flex; min-height: calc(100vh - 45px); }
  aside { width: 140px; border-right: 1px solid var(--border); padding: 12px 0; }
  aside a { display: block; padding: 7px 16px; color: var(--muted); text-decoration: none; }
  aside a.active { color: var(--text); font-weight: 600; border-left: 2px solid var(--accent); }
  main { flex: 1; padding: 16px 20px; max-width: 1100px; }
</style>
```

`SourceDetail`, `Overview`, `Export`, `Settings` 는 Task 16·17 에서 만든다. 그 전까지 빌드가 깨지므로 **Task 16 까지 마친 뒤에 빌드를 검증한다.** 이 태스크에서는 파일 작성까지만 하고 커밋한다.

- [ ] **Step 5: 커밋**

```bash
git add web/src/App.svelte web/src/components web/src/routes
git commit -m "feat: 앱 셸과 소스 목록·등록 화면 추가"
```

---

### Task 16: 문서 상세 화면 — 퍼널·수집 실행·상태 확인·이력

**Files:**
- Create: `web/src/routes/SourceDetail.svelte`
- Create: `web/src/components/RunTable.svelte`
- Create: `web/src/components/StatusBadge.svelte`

**Interfaces:**
- Consumes: `GET /api/sources/{id}`, `POST /api/sources/{id}/collect`, `GET /api/sources/{id}/runs/latest`, `POST /api/sources/{id}/update`, `POST /api/sources/{id}/archive`
- Produces: `SourceDetail.svelte` — props `{ id }`

FiftyOne "이 문서만 보기" 링크는 `${FIFTYONE_URL}/datasets/drheri?view=doc-${id}` 형태다. saved view 는 Task 18 의 배포 절차에서 만든다.

- [ ] **Step 1: 상태 배지와 이력 테이블 작성**

`web/src/components/StatusBadge.svelte`:

```svelte
<script>
  let { status } = $props();
  const COLOR = {
    SUCCESS: 'var(--training)',
    FAILURE: 'var(--rejected)',
    CANCELED: 'var(--rejected)',
    TIMEOUT: 'var(--rejected)',
    RUNNING: 'var(--accent)',
    QUEUED: 'var(--muted)',
  };
  const TEXT = {
    SUCCESS: '완료', FAILURE: '실패', CANCELED: '취소',
    TIMEOUT: '시간초과', RUNNING: '진행 중', QUEUED: '대기 중',
  };
</script>

<span style="color:{COLOR[status] ?? 'var(--muted)'}">{TEXT[status] ?? status ?? '—'}</span>
```

`web/src/components/RunTable.svelte`:

```svelte
<script>
  import StatusBadge from './StatusBadge.svelte';
  import { dateTime, num } from '../lib/format.js';

  let { runs, dagsterBase } = $props();
</script>

{#if runs.length === 0}
  <p class="label">수집 이력이 없습니다.</p>
{:else}
  <table>
    <thead>
      <tr><th>일시</th><th>설정</th><th>상태</th><th>추출</th><th></th></tr>
    </thead>
    <tbody>
      {#each runs as r (r.id)}
        <tr>
          <td>{dateTime(r.started_at)}</td>
          <td class="label">conf {r.conf} · dpi {r.dpi} · {r.pages || '전체'}</td>
          <td>
            <StatusBadge status={r.status} />
            {#if r.error}<span class="label" title={r.error}>· {r.error.slice(0, 40)}</span>{/if}
          </td>
          <td class="num">{num(r.extracted)}</td>
          <td>
            {#if r.dagster_run_id}
              <a href="{dagsterBase}/runs/{r.dagster_run_id}" target="_blank" rel="noreferrer">로그</a>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
```

- [ ] **Step 2: 상세 화면 작성**

`web/src/routes/SourceDetail.svelte`:

```svelte
<script>
  import { get, post } from '../lib/api.js';
  import FunnelBar from '../components/FunnelBar.svelte';
  import RunTable from '../components/RunTable.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { dateTime } from '../lib/format.js';
  import { loadSources, toast } from '../lib/stores.svelte.js';
  import { navigate } from '../lib/router.svelte.js';

  let { id } = $props();

  let doc = $state(null);
  let busy = $state(false);
  let editing = $state(false);
  let edit = $state({ name: '', brand: '', memo: '', conf: 0.35, dpi: 200, pages: '' });
  let settings = $state({ DAGSTER_URL: '', FIFTYONE_URL: '' });

  async function load() {
    try {
      doc = await get(`/api/sources/${id}`);
      edit = {
        name: doc.name, brand: doc.brand_raw || doc.brand, memo: doc.memo,
        conf: doc.default_conf, dpi: doc.default_dpi, pages: doc.default_pages,
      };
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  $effect(() => {
    id;                                   // id 가 바뀌면 다시 불러온다
    load();
    get('/api/settings').then((s) => (settings = s)).catch(() => {});
  });

  async function collect() {
    busy = true;
    try {
      await post(`/api/sources/${id}/collect`, {});
      toast('수집을 시작했습니다. 완료되면 자동으로 갱신됩니다.', 'info');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function checkStatus() {
    busy = true;
    try {
      const r = await get(`/api/sources/${id}/runs/latest`);
      toast(`최근 수집 상태: ${r.status}`, 'info');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function save() {
    try {
      await post(`/api/sources/${id}/update`, {
        name: edit.name, brand: edit.brand, memo: edit.memo,
        conf: Number(edit.conf), dpi: Number(edit.dpi), pages: edit.pages,
      });
      editing = false;
      await load();
      await loadSources();
      toast('저장했습니다', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function archive() {
    if (!confirm('이 문서를 보관 처리할까요? 수집된 이미지와 이력은 남습니다.')) return;
    try {
      await post(`/api/sources/${id}/archive`);
      await loadSources();
      navigate('#/sources');
    } catch (e) {
      toast(e.message, 'error');
    }
  }
</script>

{#if !doc}
  <p class="label">불러오는 중…</p>
{:else}
  <a href="#/sources" class="label">← 소스</a>

  <h2>{doc.name}</h2>
  <div class="label url">{doc.url}</div>
  <div class="label">
    브랜드 <b>{doc.brand}</b> · 등록 {dateTime(doc.created_at)}
    · 마지막 수집 {dateTime(doc.runs[0]?.started_at)}
    {#if doc.runs[0]}<StatusBadge status={doc.runs[0].status} />{/if}
    {#if doc.status === 'archived'}<b class="archived">보관됨</b>{/if}
  </div>

  <div class="funnel"><FunnelBar funnel={doc.funnel} height={14} /></div>

  <div class="actions">
    <button class="primary" onclick={collect} disabled={busy}>수집 실행</button>
    <button onclick={checkStatus} disabled={busy}>상태 확인</button>
    <a class="btn" href="{settings.FIFTYONE_URL}/datasets/drheri?view=doc-{doc.id}"
       target="_blank" rel="noreferrer">FiftyOne 에서 이 문서만 보기</a>
    <button onclick={() => (editing = !editing)}>{editing ? '취소' : '수정'}</button>
    <button onclick={archive}>보관</button>
  </div>

  {#if editing}
    <div class="edit">
      <div class="row">
        <div><div class="label">이름</div><input bind:value={edit.name} /></div>
        <div><div class="label">브랜드</div><input bind:value={edit.brand} /></div>
      </div>
      <div class="row">
        <div><div class="label">conf</div><input bind:value={edit.conf} /></div>
        <div><div class="label">dpi</div><input bind:value={edit.dpi} /></div>
        <div><div class="label">페이지</div><input bind:value={edit.pages} /></div>
      </div>
      <div class="label">메모</div>
      <input bind:value={edit.memo} />
      <div class="actions"><button class="primary" onclick={save}>저장</button></div>
    </div>
  {:else if doc.memo}
    <p class="memo">{doc.memo}</p>
  {/if}

  <h3>수집 이력</h3>
  <RunTable runs={doc.runs} dagsterBase={settings.DAGSTER_URL} />
  <p class="label">같은 이미지는 content_hash 로 중복 제거됩니다 — 재수집해도 퍼널이 부풀지 않습니다.</p>
{/if}

<style>
  h2 { font-size: 16px; margin: 10px 0 2px; }
  h3 { font-size: 13px; margin: 20px 0 6px; }
  .url { word-break: break-all; }
  .funnel { margin: 14px 0; max-width: 620px; }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0; align-items: center; }
  .btn { padding: 6px 12px; border: 1px solid var(--border); border-radius: 4px;
         color: var(--text); text-decoration: none; }
  .edit { border: 1px solid var(--border); border-radius: 6px; padding: 12px; max-width: 620px; }
  .row { display: flex; gap: 6px; margin-bottom: 6px; }
  .row > * { flex: 1; }
  .memo { color: var(--muted); }
  .archived { color: var(--rejected); margin-left: 6px; }
</style>
```

- [ ] **Step 3: 커밋**

```bash
git add web/src/routes/SourceDetail.svelte web/src/components/RunTable.svelte \
        web/src/components/StatusBadge.svelte
git commit -m "feat: 문서 상세 화면 추가 (퍼널·수집 실행·상태 확인·이력)"
```

---

### Task 17: 현황 · 학습데이터 · 설정 화면 + 빌드 검증

**Files:**
- Create: `web/src/routes/Overview.svelte`
- Create: `web/src/routes/Export.svelte`
- Create: `web/src/routes/Settings.svelte`

**Interfaces:**
- Consumes: `GET /api/overview`, `GET /api/export/summary`, `POST /api/export`, `GET|POST /api/settings`, `POST /api/fiftyone/restart`

- [ ] **Step 1: 현황 화면**

`web/src/routes/Overview.svelte`:

```svelte
<script>
  import { get } from '../lib/api.js';
  import FunnelBar from '../components/FunnelBar.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { dateTime, num } from '../lib/format.js';
  import { toast } from '../lib/stores.svelte.js';

  let data = $state(null);

  $effect(() => {
    get('/api/overview').then((d) => (data = d)).catch((e) => toast(e.message, 'error'));
  });
</script>

<h2>현황</h2>

{#if !data}
  <p class="label">불러오는 중…</p>
{:else}
  <div class="funnel"><FunnelBar funnel={data.funnel} height={14} /></div>

  <div class="label">
    FiftyOne: {data.services.fiftyone.ok ? '정상' : `이상 — ${data.services.fiftyone.detail}`}
    (포트 {data.services.fiftyone.port})
  </div>

  <h3>최근 수집</h3>
  <table>
    <thead><tr><th>일시</th><th>문서</th><th>상태</th><th>추출</th></tr></thead>
    <tbody>
      {#each data.recent_runs as r (r.id)}
        <tr>
          <td>{dateTime(r.started_at)}</td>
          <td><a href="#/sources/{r.document_id}">{r.document_name}</a></td>
          <td><StatusBadge status={r.status} /></td>
          <td class="num">{num(r.extracted)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  h2 { font-size: 15px; margin: 0 0 12px; }
  h3 { font-size: 13px; margin: 20px 0 6px; }
  .funnel { max-width: 620px; margin-bottom: 10px; }
</style>
```

- [ ] **Step 2: 학습데이터 화면**

`web/src/routes/Export.svelte`:

```svelte
<script>
  import { get, post } from '../lib/api.js';
  import { num } from '../lib/format.js';
  import { toast } from '../lib/stores.svelte.js';

  let dist = $state(null);
  let busy = $state(false);
  let result = $state(null);

  async function load() {
    try {
      dist = await get('/api/export/summary');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  $effect(() => { load(); });

  async function run() {
    busy = true;
    try {
      result = await post('/api/export');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }
</script>

<h2>학습데이터</h2>

<button class="primary" onclick={run} disabled={busy}>
  {busy ? '생성 중…' : 'DGX 내보내기 생성'}
</button>

{#if result}
  <p class="label">{result.rows}행 · {result.labels_tsv} · {result.manifest_jsonl}</p>
{/if}

{#if dist}
  <p class="label">학습 이미지 {num(dist.total)}장</p>
  <div class="cols">
    {#each [['브랜드', dist.brands], ['시리즈', dist.series], ['모델', dist.models]] as [title, rows] (title)}
      <div>
        <h3>{title}</h3>
        <table>
          <tbody>
            {#each rows.slice(0, 20) as r (r.name)}
              <tr><td>{r.name}</td><td class="num">{num(r.count)}</td></tr>
            {/each}
          </tbody>
        </table>
        {#if rows.length > 20}<p class="label">외 {rows.length - 20}종</p>{/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  h2 { font-size: 15px; margin: 0 0 12px; }
  h3 { font-size: 12px; margin: 14px 0 4px; color: var(--muted); }
  .cols { display: flex; gap: 24px; align-items: flex-start; }
  .cols > div { flex: 1; }
</style>
```

- [ ] **Step 3: 설정 화면**

`web/src/routes/Settings.svelte`:

```svelte
<script>
  import { get, post } from '../lib/api.js';
  import { toast } from '../lib/stores.svelte.js';

  const FIELDS = [
    ['DEFAULT_CONF', '기본 conf'],
    ['DEFAULT_DPI', '기본 dpi'],
    ['DAGSTER_URL', 'Dagster 주소'],
    ['FIFTYONE_URL', 'FiftyOne 주소'],
    ['FIFTYONE_SERVICE', 'FiftyOne systemd 서비스명'],
  ];

  let values = $state({});
  let dataRoot = $state('');
  let busy = $state(false);

  $effect(() => {
    get('/api/settings')
      .then((s) => { values = s; dataRoot = s.DATA_ROOT; })
      .catch((e) => toast(e.message, 'error'));
  });

  async function save() {
    busy = true;
    try {
      values = await post('/api/settings', values);
      toast('저장했습니다', 'success');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function restart() {
    busy = true;
    try {
      const r = await post('/api/fiftyone/restart');
      toast(r.ok ? `재기동 완료 (잔여 정리 ${r.orphans_killed}건)` : `재기동 실패: ${r.detail}`,
            r.ok ? 'success' : 'error');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }
</script>

<h2>설정</h2>

{#each FIELDS as [key, label] (key)}
  <div class="label">{label}</div>
  <input bind:value={values[key]} />
{/each}

<div class="label">데이터 경로 (환경변수 DATA_ROOT 로만 변경)</div>
<input value={dataRoot} readonly />

<div class="actions">
  <button class="primary" onclick={save} disabled={busy}>저장</button>
  <button onclick={restart} disabled={busy}>FiftyOne 재기동</button>
</div>

<style>
  h2 { font-size: 15px; margin: 0 0 12px; }
  .label { margin: 10px 0 4px; }
  input { max-width: 480px; }
  .actions { display: flex; gap: 6px; margin-top: 16px; }
</style>
```

- [ ] **Step 4: 빌드 검증**

Run: `cd web && npm run build`
Expected: 오류 없이 `dist/index.html` 과 `dist/assets/*.js` 생성

Run: `cd web && npm test`
Expected: PASS (10 passed)

- [ ] **Step 5: 커밋**

```bash
git add web/src/routes/Overview.svelte web/src/routes/Export.svelte web/src/routes/Settings.svelte
git commit -m "feat: 현황·학습데이터·설정 화면 추가"
```

---

### Task 18: 정적 서빙 전환 · 구버전 제거 · 배포

**Files:**
- Modify: `drheri_pipeline/ui/app.py`
- Delete: `drheri_pipeline/ui/templates/index.html`
- Delete: `drheri_pipeline/ui/registry.py`
- Delete: `scripts/promote_reviewed.py`, `scripts/promote_reviewed.sh`
- Create: `scripts/fiftyone_saved_views.py`
- Modify: `scripts/setup_ui_root.sh`
- Test: `tests/test_static_serving.py`

**Interfaces:**
- Produces:
  - `app.create_app()` — `/api/*` 라우트 + `/` 이하 `web/dist` 정적 서빙 (없으면 안내 JSON)
  - `fiftyone_saved_views.sync_views() -> int` — 문서별 saved view (`doc-<id>`) 생성/갱신, 만든 뷰 수 반환

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_static_serving.py`:

```python
import pytest
from starlette.testclient import TestClient

from drheri_pipeline.ui import app as ui_app


@pytest.fixture()
def client(data_root):
    return TestClient(ui_app.create_app())


def test_api_routes_still_work(client):
    assert client.get("/api/health").json()["ok"] is True


def test_root_returns_helpful_message_when_not_built(client, monkeypatch):
    monkeypatch.setattr(ui_app, "DIST", ui_app.DIST.parent / "nonexistent-dist")
    c = TestClient(ui_app.create_app())
    body = c.get("/").json()
    assert body["ok"] is False
    assert "npm run build" in body["error"]["message"]


def test_registry_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import drheri_pipeline.ui.registry  # noqa: F401
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/bin/python -m pytest tests/test_static_serving.py -v`
Expected: FAIL — `AttributeError: module 'drheri_pipeline.ui.app' has no attribute 'DIST'` 및
`test_registry_module_is_gone` 실패(모듈이 아직 존재)

- [ ] **Step 3: 앱 최종본 작성**

`drheri_pipeline/ui/app.py` 전체를 아래로 교체한다.

```python
"""Dr.HERi 데이터 파이프라인 관리 UI — JSON API + 정적 SPA 서빙.

실행: uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000
화면 빌드: cd web && npm run build   (→ web/dist)
"""
from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from drheri_pipeline.db import conn
from drheri_pipeline.ui.api import ops, runs, sources
from drheri_pipeline.ui.envelope import ApiError, api_error_handler, fail, unhandled_error_handler

DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


async def spa(request: Request):
    """SPA 진입점. 라우팅은 해시로 하므로 index.html 하나면 충분하다."""
    index = DIST / "index.html"
    if not index.exists():
        return fail("ui_not_built",
                    "화면이 아직 빌드되지 않았습니다. `cd web && npm run build` 를 실행하세요.",
                    status=503)
    return FileResponse(index)


def create_app() -> Starlette:
    conn.migrate()
    routes = [*sources.routes, *runs.routes, *ops.routes]
    if (DIST / "assets").exists():
        routes.append(Mount("/assets", app=StaticFiles(directory=DIST / "assets")))
    routes.append(Route("/", spa, methods=["GET"]))
    return Starlette(
        routes=routes,
        exception_handlers={ApiError: api_error_handler, Exception: unhandled_error_handler},
    )


app = create_app()
```

- [ ] **Step 4: 구버전 제거**

```bash
cd /c/dev/Dr.HERi/data-pipeline
git rm drheri_pipeline/ui/templates/index.html drheri_pipeline/ui/registry.py \
       scripts/promote_reviewed.py scripts/promote_reviewed.sh
rmdir drheri_pipeline/ui/templates 2>/dev/null || true
```

`registry` 를 참조하는 코드가 남아 있지 않은지 확인한다.

Run: `grep -rn "registry\|promote_reviewed" drheri_pipeline scripts tests --include=*.py`
Expected: 결과 없음

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests -v`
Expected: PASS (62 passed)

- [ ] **Step 6: FiftyOne saved view 스크립트 작성**

`scripts/fiftyone_saved_views.py`:

```python
"""문서별 FiftyOne saved view 생성 — 상세 화면의 "이 문서만 보기" 링크 대상.

뷰 이름은 doc-<document_id>. 기존 뷰는 덮어쓴다(뷰 정의만 갱신, 샘플은 건드리지 않음).
실행: FIFTYONE_DATABASE_VALIDATION=false .venv/bin/python -m scripts.fiftyone_saved_views
"""
from __future__ import annotations

from drheri_pipeline.db import conn

DATASET = "drheri"


def sync_views() -> int:
    import fiftyone as fo
    from fiftyone import ViewField as F

    if DATASET not in fo.list_datasets():
        return 0
    ds = fo.load_dataset(DATASET)

    with conn.session() as cx:
        rows = cx.execute("SELECT id, name FROM document WHERE status='active'").fetchall()
        origins = {r["id"]: [x["content_hash"] for x in cx.execute(
            "SELECT content_hash FROM image_origin WHERE document_id=?", (r["id"],)).fetchall()]
            for r in rows}

    made = 0
    for r in rows:
        hashes = origins.get(r["id"]) or []
        if not hashes:
            continue
        name = f"doc-{r['id']}"
        if name in ds.list_saved_views():
            ds.delete_saved_view(name)
        ds.save_view(name, ds.match(F("content_hash").is_in(hashes)),
                     description=r["name"])
        made += 1

    # 버림 전용 뷰 — 오판 복구용
    if "버림" in ds.list_saved_views():
        ds.delete_saved_view("버림")
    ds.save_view("버림", ds.match(F("stage") == "rejected"), description="버림 처리된 이미지")
    return made


if __name__ == "__main__":
    print(f"saved views {sync_views()}개 생성")
```

- [ ] **Step 7: systemd 유닛 갱신**

`scripts/setup_ui_root.sh` 의 UI 서비스 유닛에 환경변수를 추가한다. `[Service]` 블록에 다음 줄들이 포함되어야 한다.

```ini
Environment=DATA_ROOT=/home/jay8126/Dr.HERi/data-pipeline/data
Environment=FIFTYONE_DATABASE_VALIDATION=false
Environment=HOOK_TOKEN=drheri-dev
Environment=UI_BASE_URL=http://127.0.0.1:3000
Environment=DAGSTER_URL=http://58.229.105.3:3333
Environment=FIFTYONE_URL=http://58.229.105.3:5151
```

Dagster 서비스 유닛(`scripts/setup_systemd_root.sh`)에도 센서가 훅을 보낼 수 있도록 같은 `HOOK_TOKEN` 과 `UI_BASE_URL` 을 추가한다.

- [ ] **Step 8: 커밋**

```bash
git add drheri_pipeline/ui/app.py scripts/fiftyone_saved_views.py scripts/setup_ui_root.sh \
        scripts/setup_systemd_root.sh tests/test_static_serving.py
git commit -m "refactor: Jinja2 화면 제거하고 Svelte 정적 서빙으로 전환"
```

- [ ] **Step 9: 개발서버 배포 (수동)**

개발서버 58.229.105.3 (jay8126) 에서 순서대로 실행한다.

```bash
cd ~/Dr.HERi/data-pipeline
git pull

# 1) 백필 — 먼저 백업
cp data/manifest.jsonl data/manifest.jsonl.bak
cp data/sources.jsonl data/sources.jsonl.bak
.venv/bin/python -m scripts.backfill_db

# 2) 화면 빌드
cd web && npm install && npm run build && cd ..

# 3) saved view 생성
FIFTYONE_DATABASE_VALIDATION=false .venv/bin/python -m scripts.fiftyone_saved_views

# 4) 서비스 재기동 (root: su -)
su - -c "bash /home/jay8126/Dr.HERi/data-pipeline/scripts/setup_ui_root.sh"
su - -c "systemctl restart drheri-dagster drheri-ui"
```

검증:

```bash
curl -s http://127.0.0.1:3000/api/health
curl -s http://127.0.0.1:3000/api/sources | head -c 400
```
Expected: 첫 명령이 `{"ok": true, "data": {"db": true, ...}}`, 두 번째가 백필된 브랜드·문서 트리.

브라우저에서 `http://58.229.105.3:3000` 을 열어 확인한다.
1. 소스 목록에 브랜드 › 문서와 퍼널이 보이는가
2. 문서 상세에서 `수집 실행` → 완료 시 **새로고침 없이** 토스트가 뜨고 퍼널이 갱신되는가
3. FiftyOne 에서 태그를 찍고 `검수결과 반영` 을 누르면 학습/버림 숫자가 바뀌는가
4. 재기동 후 `pgrep -af "[f]iftyone" | wc -l` 이 1인가

- [ ] **Step 10: 최종 커밋**

```bash
git add -A
git commit -m "docs: 파이프라인 UI 재설계 배포 완료"
```

---

## 완료 기준

- [ ] `.venv/bin/python -m pytest tests -v` 전부 통과 (62건)
- [ ] `cd web && npm test && npm run build` 성공
- [ ] 개발서버 3000 에서 소스 트리·퍼널·수집 실행·검수 동기화가 동작
- [ ] 수집 완료가 폴링 없이 SSE 로 화면에 반영
- [ ] FiftyOne 재기동 후 잔여 프로세스 0, mongod 생존
- [ ] `registry.py` / Jinja2 템플릿 / `promote_reviewed.py` 제거됨
