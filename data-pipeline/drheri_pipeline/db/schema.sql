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
  is_fixture   INTEGER,
  diameter     TEXT,
  diameter_src TEXT,
  needs_review INTEGER NOT NULL DEFAULT 0,
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
