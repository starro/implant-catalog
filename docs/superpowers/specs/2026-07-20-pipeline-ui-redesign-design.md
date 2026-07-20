# Dr.HERi 데이터 파이프라인 관리 UI 재설계

- 작성일: 2026-07-20
- 상태: 설계 승인됨
- 대상: `data-pipeline/drheri_pipeline/ui` (개발서버 58.229.105.3, 포트 3000)

## 1. 배경과 문제

현재 UI 는 Starlette + Jinja2 단일 화면이다. 수집 폼·전체 현황·수집 이력이 한 페이지에 섞여 있고,
실행 상태를 알리려고 5초마다 페이지를 통째로 새로고침한다. 세 가지가 한계다.

1. **성격이 다른 작업이 한 화면에 있다** — 소스 등록/보관, 수집 실행, 검수 결과 확인, 학습데이터 내보내기는
   각각 다른 리듬의 작업인데 한 화면으로 눌러 담아 어느 것도 제대로 표현되지 않는다.
2. **소스가 1급 객체가 아니다** — URL 이 수집 이력의 한 컬럼일 뿐이라, "이 카탈로그에서 몇 장을 뽑았고 그중
   몇 장이 학습데이터가 됐나"를 볼 수 없다. 이것이 이 도구의 핵심 가치인데 빠져 있다.
3. **버림(reject)이 어디에도 기록되지 않는다** — review/training 디렉토리만 존재해, FiftyOne 에서 버린 이미지는
   흔적 없이 사라진다. 퍼널을 닫을 수 없다.

## 2. 목표 / 비목표

**목표**
- 소스(카탈로그 문서)를 1급 객체로 등록·보관하고, 소스별 퍼널(추출 → 학습 / 버림 / 대기)을 추적한다.
- 수집 실행과 완료 감지를 폴링 없이 처리한다.
- FiftyOne 검수 결과(판정·라벨)를 버튼 한 번으로 우리 데이터에 반영한다.
- 운영 데이터를 SQLite 로 옮겨 집계·조회를 가능하게 한다.

**비목표 (이번 범위 밖)**
- 자체 UI 내 이미지 그리드 / 라벨링 기능 — 이미지 보기와 라벨링은 전부 FiftyOne 이 담당한다. (다음 단계)
- 사용자 인증 — 사내망 전용.
- DGX 학습 파이프라인 연동 — 내보내기 산출물 생성까지만.

## 3. 확정된 설계 결정

| 항목 | 결정 |
|---|---|
| 주 작업 | 수집 실행·관리 (라벨링은 FiftyOne) |
| 소스 모델 | 등록·보관하는 엔티티 (URL 1개 = 문서 1개) |
| 계층 | 브랜드 › 문서(PDF) 2단계 |
| 핵심 지표 | 소스별 퍼널: 추출 / 학습 / 버림 / 대기 |
| 검수 동기화 | 버튼 한 번 수동 실행 |
| 저장소 | SQLite 운영 DB. jsonl/tsv 는 DGX 내보내기 산출물로 강등 |
| 완료 감지 | Dagster run_status_sensor → 훅 → SSE 푸시 + 수동 `상태 확인` 버튼 |
| 프론트엔드 | Svelte 5 (runes) + JSON API, SPA |
| 디자인 | 미니멀 실무형 (흰 배경·얇은 선·높은 정보밀도) |

## 4. 화면 구조 (IA)

**상단바(고정)**: `Dr.HERi 데이터 파이프라인` · `Dagster ↗` `FiftyOne ↗` 링크 · `[검수결과 반영]` 버튼(전역)

**좌측 사이드바 — 4개 메뉴**

| 메뉴 | 경로 | 역할 |
|---|---|---|
| 소스 (기본) | `#/sources` | 브랜드 › 문서 트리 + 문서별 퍼널, 새 소스 등록 |
| 현황 | `#/overview` | 전체 퍼널 합계, 최근 수집 실행, 서비스 상태 |
| 학습데이터 | `#/export` | DGX 내보내기, 브랜드·시리즈·모델 클래스 분포 |
| 설정 | `#/settings` | 기본 수집값, 데이터 경로, 외부 URL, FiftyOne 수동 재기동 |

### 4.1 소스 화면

- 브랜드가 접이식 그룹 헤더. 브랜드 합산 퍼널 바를 표시한다.
- 그 아래 문서(PDF) 행. 문서별 퍼널 `추출 / 학습 / 버림 / 대기`.
- 상단 `[+ 새 카탈로그 등록]`. URL 입력 중 중복이면 즉시 경고하고 기존 문서로 가는 링크를 준다.
- 브랜드 전용 등록 화면은 없다. 문서 등록 시 브랜드명을 입력하면 taxonomy 정규화(`Osstem` → `OSSTEM IMPLANT`)
  후 없으면 자동 생성한다.

### 4.2 문서 상세

- 헤더: 문서명 · URL · 브랜드 · 등록일 · 마지막 수집
- 퍼널 바 + 4개 숫자
- 액션: `수집 실행` / `상태 확인` / `FiftyOne에서 이 문서만 보기` / `수정` / `보관`
- 수집 이력 테이블: 일시 · 설정(conf/dpi/pages) · 상태 · 추출수 · 로그

## 5. 데이터 모델 (SQLite)

파일 하나 `data/pipeline.db`, WAL 모드. 쓰기 주체는 Dagster 수집 잡과 UI 서버 둘뿐이다.

```sql
brand            -- 브랜드
  id, name_norm UNIQUE, name_raw, created_at

document         -- 소스 1건 = URL 1개
  id, brand_id, name, url UNIQUE, source_type,      -- catalog_pdf | site_xray
  default_conf, default_dpi, default_pages, default_series,
  memo, status,                                      -- active | archived
  created_at, updated_at

run              -- 수집 실행 1회
  id, document_id, dagster_run_id,
  conf, dpi, pages,
  status,                                            -- QUEUED|RUNNING|SUCCESS|FAILURE|TIMEOUT
  extracted, started_at, finished_at, error

image            -- 이미지 1장 = content_hash 1개 (전역 유일)
  content_hash PK, ext, width, height,
  brand, series, model, modality,                    -- 라벨
  review_state,                                      -- pending | kept | rejected
  reject_reason, reviewed_at,
  stage,                                             -- review | training | rejected
  rel_path, created_at

image_origin     -- 출처 추적: 이 이미지가 어느 문서 어느 페이지에서 나왔나
  content_hash, document_id, run_id, page_no, bbox,
  PRIMARY KEY (content_hash, document_id)

sync_log         -- 검수 동기화 실행 기록
  id, started_at, finished_at, kept, rejected, promoted, note
```

**`image` / `image_origin` 분리 이유**: 동일 이미지가 두 카탈로그에 모두 실려 있으면 `content_hash` 는 하나지만
출처는 둘이다. 분리하면 중복 저장 없이 두 문서 퍼널에 모두 잡히고, 학습 이미지의 원본 출처를 역추적할 수 있다.

### 5.1 퍼널 산식

문서 기준으로 계산하고 브랜드는 합산한다.

| 지표 | 산식 |
|---|---|
| 추출 | `image_origin` 의 해당 문서 행 수 |
| 학습 | 그중 `stage = 'training'` |
| 버림 | 그중 `review_state = 'rejected'` |
| 대기 | 추출 − 학습 − 버림 |

`대기` 는 뺄셈으로 정의한다. keep 했지만 `model` 이 비어 승급하지 못한 건이 어느 칸에도 안 잡히는 일을 막기
위해서다. 툴팁에서 `미검수 N · 라벨 미완 N` 으로 쪼개 보여준다.

### 5.2 저장소 전환

- `manifest.jsonl` 은 더 이상 진실의 원천이 아니라 SQLite 에서 생성하는 DGX 내보내기 산출물이다.
- 기존 `manifest.jsonl` 과 `sources.jsonl` 은 최초 1회 SQLite 로 백필한다. 백필 스크립트는 멱등해야 한다.
- 백필 이후 파이프라인(Dagster 애셋)은 SQLite 에 직접 쓴다.

## 6. JSON API

응답 봉투는 `{ ok, data, error }` 로 통일한다. 메서드는 GET/POST 만 쓴다.

**소스**

| 메서드 · 경로 | 용도 |
|---|---|
| `GET /api/sources` | 브랜드 › 문서 트리 + 각 퍼널 |
| `GET /api/sources/check?url=` | 중복 URL 확인 → 기존 문서 id |
| `POST /api/sources` | 문서 등록 (브랜드 없으면 정규화 후 자동 생성) |
| `GET /api/sources/{id}` | 상세 — 메타 · 퍼널 · 수집 이력 |
| `POST /api/sources/{id}/update` | 이름/브랜드/기본설정/메모 수정 |
| `POST /api/sources/{id}/archive` | 보관 (soft delete, 이미지·이력 유지) |

**수집**

| 메서드 · 경로 | 용도 |
|---|---|
| `POST /api/sources/{id}/collect` | Dagster 잡 제출 → run 행 생성, `run_id` 반환 |
| `GET /api/sources/{id}/runs/latest` | 수동 `상태 확인` — RUNNING 이면 Dagster 1회 조회 후 정정 |
| `GET /api/runs/{id}/log` | Dagster 로그 URL/요약 |

**푸시**

| 메서드 · 경로 | 용도 |
|---|---|
| `GET /api/events` | SSE — `run.finished`, `sync.finished`, `export.finished` |
| `POST /api/hooks/run-finished` | Dagster 센서 전용. 공유 토큰 헤더 검증 |

**동기화 · 내보내기 · 기타**

| 메서드 · 경로 | 용도 |
|---|---|
| `POST /api/sync` | FiftyOne 검수결과 반영. 결과: kept/rejected/promoted 수 |
| `GET /api/overview` | 전체 퍼널 · 최근 런 · 서비스 상태 |
| `GET /api/export/summary` | 클래스 분포, 마지막 내보내기 시각 |
| `POST /api/export` | `labels.tsv` + `manifest.jsonl` 생성 |
| `GET /api/settings` · `POST /api/settings` | 기본 conf/dpi, 경로, 외부 URL |
| `POST /api/fiftyone/restart` | 수동 재기동 |
| `GET /api/health` | 자체 헬스체크 |

**서버 구성**: 기존 Starlette 유지(Jinja2 템플릿 제거), 빌드된 Svelte 를 `/` 에서 정적 서빙 + `/api/*`.
프로세스는 uvicorn 하나(`drheri-ui.service`), 포트 3000.

**인증**: 사내망 전용이라 사용자 인증은 두지 않는다. `/api/hooks/*` 만 공유 토큰으로 막는다.

## 7. 완료 감지 (폴링 제거)

```
Dagster (@run_status_sensor)          데몬이 RUN_SUCCESS/RUN_FAILURE 시 발화
   └─ POST /api/hooks/run-finished    → UI 서버
        ├─ run 행 갱신 + 이미지 집계
        ├─ FiftyOne 재기동 (§9 절차)
        └─ SSE 'run.finished' 발행 → 브라우저의 해당 행만 갱신 + 토스트
```

- 기존 `_watch_run` 의 5초 GraphQL 폴링 루프와 브라우저 meta refresh 를 모두 제거한다.
- **보정(reconcile)**: 센서 알림을 놓친 경우(UI 재시작 등)에 대비해, 소스 화면 진입 시 `RUNNING` 으로 남은 런이
  있으면 그때 1회만 Dagster 에 상태를 물어 정정한다. 상시 폴링이 아니다.
- 수동 `상태 확인` 버튼도 같은 정정 경로를 쓴다.

## 8. FiftyOne 검수 동기화

**검수자가 FiftyOne 에서 하는 일**
1. 태그로 판정 — `keep` / `reject`
2. 라벨 필드 직접 수정 — `brand` / `series` / `model`

**`POST /api/sync` 동작 순서**

1. venv 파이썬으로 sync 스크립트 실행 (`FIFTYONE_DATABASE_VALIDATION=false`)
2. 데이터셋 `drheri` 전체 순회. 키는 샘플에 저장된 `content_hash`
3. 판정 반영
   - `reject` 태그 → `review_state='rejected'`, `stage='rejected'`, 파일을 `data/rejected/` 로 **이동**(삭제 아님)
   - `keep` 태그 → `review_state='kept'`
   - 태그 없음 → `pending` 유지
4. 라벨 반영 — `brand/series/model` 을 taxonomy 로 정규화 후 SQLite 갱신
5. 승급 — `kept` + 라벨 3종 완비 → `stage='training'`, 파일을 training 계층으로 이동
   (기존 `promote_reviewed.py` 를 흡수)
6. `sync_log` 기록 → SSE `sync.finished` → 화면 퍼널 갱신

**반대 방향(SQLite → FiftyOne)은 항상 증분**: 수집 후 FiftyOne 재기동 시 데이터셋을 재생성하지 않고 새 샘플만
추가한다. 전체 재빌드로 태그·수정이 소실되고 데이터셋이 깨졌던 과거 문제를 차단한다. 버림 샘플은 삭제하지 않고
기본 뷰에서만 제외하며, `버림` saved view 로 오판을 되돌릴 수 있다.

**"이 문서만 보기"**: 샘플에 `document_id` 를 심고, 문서 상세 버튼이 해당 필터가 걸린 saved view 링크로 이동한다.

**동시 편집**: 동기화 중 찍힌 태그는 다음 동기화에 반영된다. 잠금은 걸지 않고, 진행 중이면 버튼을 비활성화한다.

## 9. FiftyOne 재기동 절차 (필수)

과거 로컬에서 앱 하나당 파이썬 프로세스가 다수 남아 데이터셋이 주기적으로 초기화되던 문제가 있었다.
재기동은 반드시 다음 4단계를 밟는다.

```
① systemctl stop drheri-fiftyone
② 잔여 프로세스 강제 종료 — cmdline 타깃 트리 종료
     pkill -f "[f]iftyone.server" ; pkill -f "[f]iftyone.core.service"
   - 포트 기준 kill 금지 (리스너만 죽고 자식 세션이 남아 상태가 꼬임)
   - mongod 는 종료하지 않는다 (데이터 유실)
   - 브래킷 표기로 자기 자신 매치를 피한다
③ systemctl start drheri-fiftyone
④ 헬스체크 — 5151 응답 + 샘플 수 확인. 실패 시 UI 에 에러 배지
```

`POST /api/fiftyone/restart` 와 수집 완료 훅은 **같은 함수 하나**를 호출한다. 경로를 갈라두지 않는다.

## 10. 프론트엔드 구조

Vite + Svelte 5 (runes), SPA. `npm run build` → `dist/` 를 Starlette 가 정적 서빙.

```
web/src/
  lib/api.js              fetch 래퍼 ({ok,data,error} 언랩, 에러 토스트)
  lib/events.js           SSE 구독 → 스토어 갱신
  lib/stores.svelte.js    $state 기반 sources / overview / toast
  lib/format.js           숫자·일시(Asia/Seoul)·퍼널 계산
  components/             FunnelBar · BrandGroup · DocumentRow · RunTable ·
                          Modal · Toast · StatusBadge
  routes/                 Sources · SourceDetail · Overview · Export · Settings
```

라우팅은 의존성 없는 해시 라우터(`#/sources/12`). 서버 설정이 필요 없다.

### 10.1 디자인 토큰 (미니멀 실무형)

| 항목 | 값 |
|---|---|
| 배경 / 보더 | `#ffffff` / `#e5e7eb` |
| 본문 / 보조 텍스트 | `#111827` / `#6b7280` |
| 액센트(추출·버튼) | `#2563eb` |
| 학습 / 버림 / 대기 | `#059669` / `#dc2626` / `#e5e7eb` |
| 폰트 | 시스템 UI. 본문 13px, 라벨 11px, 숫자 tabular-nums |
| 여백 · 행 높이 | 4px 배수 · 36px |

퍼널 바는 4색 누적 막대 하나로 통일하고, 목록·상세·현황이 같은 컴포넌트를 공유한다.

## 11. 배포 환경

개발서버 58.229.105.3 의 포트 사용 현황을 확인했다(2026-07-20).

| 포트 | 용도 |
|---|---|
| 80 / 443 | nginx — heri2go 프론트엔드는 전부 여기서 정적 서빙 (`adms-dev`, `lab-dev`/`clinic-dev`, `intro-dev`) |
| 8090 | heri2go api-service (nginx 가 `apis-dev` 로 프록시) |
| 8080 | Jenkins · 5000 json-server · 3306 MariaDB · 1521 · 3389 · 5500 · 9900 · 16551 |
| **3000** | **Dr.HERi 관리 UI** |
| 3333 | Dagster · 5151 FiftyOne · 27017 mongod |

heri2go 레포의 `devServer.port` (admin 3000 / user 80)는 개발자 로컬 PC 전용 설정이라 서버와 무관하다.
따라서 **3000 사용에 충돌이 없다.**

## 12. 마이그레이션 순서

1. SQLite 스키마 생성 + 백필 스크립트 (manifest.jsonl / sources.jsonl → DB). 멱등.
2. 파이프라인(Dagster 애셋)이 SQLite 에 쓰도록 변경. jsonl 쓰기는 내보내기로 이관.
3. JSON API 구현 (Jinja2 라우트와 당분간 공존).
4. Svelte 프론트엔드 구현 + 정적 서빙 전환. Jinja2 템플릿 제거.
5. Dagster run_status_sensor + 훅 + SSE 연결. `_watch_run` 폴링 제거.
6. sync 스크립트 통합(판정 + 라벨 + 승급) 및 `promote_reviewed.py` 정리.

## 13. 에러 처리

- API 는 예외를 `{ ok:false, error:{ code, message } }` 로 반환하고 프론트는 토스트로 표시한다.
- Dagster 제출 실패 → `run` 행을 남기지 않고 폼에 즉시 에러 표시.
- 훅 미수신으로 런이 `RUNNING` 에 30분 이상 머무르면 화면 진입 시 정정에서 `TIMEOUT` 처리.
- FiftyOne 재기동 실패 → 수집 자체는 성공으로 두고 상단에 에러 배지. 수동 재기동 버튼으로 복구.
- sync 스크립트 실패 → `sync_log` 에 실패 사유 기록, DB 는 트랜잭션으로 롤백.

## 14. 테스트

- 퍼널 산식: 이미지가 두 문서에 걸친 경우, 버림/승급 후 합계가 어긋나지 않는지 단위 테스트.
- 백필 멱등성: 같은 manifest 를 두 번 백필해도 행 수가 변하지 않는지.
- taxonomy 정규화: 브랜드 별칭 → 정규명, `series + surface` 합성.
- 증분 반영: 재기동 후에도 기존 태그·라벨이 보존되는지.
- 재기동 절차: 정지 후 잔여 fiftyone 프로세스가 0인지 확인.
