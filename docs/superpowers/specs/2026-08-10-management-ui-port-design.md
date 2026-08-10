# 관리 UI 이식 — 새 DGX 라벨링 엔진용 컨트롤 플레인

- 작성일: 2026-08-10
- 상태: 설계 승인 대기
- 대상: `data-pipeline` 관리 UI/오케스트레이션을 새 엔진(GDINO+Qwen+geom)에 맞게 재배선, DGX 호스트 배치
- 관련: `2026-08-07-dgx-catalog-labeling-engine-design.md`(엔진), 메모리 `project_dgx_catalog_labeling_pipeline`

## 1. 배경과 문제

새 라벨링 엔진(`drheri_pipeline/labeling/`, CLI `label_catalog`)은 DGX 컨테이너에서 GPU로 돌고
검수는 DGX 호스트 FiftyOne(:5151)에서 한다. 지금은 **CLI로만** 실행 — 소스 등록·실행·진행상황을
웹에서 다룰 관제 화면이 없다.

기존 관리 시스템(Svelte SPA + Starlette API + SQLite + Dagster)은 **옛 추출방식(DocLayout)**에
배선돼 있고 개발서버(58.229.105.3)에 있으며, 새 엔진과 연결되지 않는다. 이걸 새 엔진에 맞게
재배선해 DGX 호스트에 올린다.

핵심: 주변 인프라(SPA·Starlette API·SQLite·업로드·SSE·단계별현황)는 **거의 그대로 재사용**하고,
바뀌는 것은 (a)실행부(Dagster → 경량 async 실행), (b)실행위치(DGX 컨테이너 엔진), (c)새 엔진
신호(is_fixture/diameter/needs_review) 반영, (d)UI 용어 한국어화다.

## 2. 목표 / 비목표

**목표**
- DGX 호스트에 관리 UI(웹, IP 접속)를 올려 **소스 등록·수집 실행·단계별 현황·런 이력·학습셋 export**를 웹에서 한다.
- 수집 실행은 **무중단**으로 컨테이너 엔진을 트리거하고, 런별 임시데이터는 **즉시 정리**한다(고아 없음).
- 실제 이미지 검수는 FiftyOne(:5151)이 담당 — 관리 UI는 그 링크만 제공(2-플레인).
- UI 용어를 한국어로("퍼널"→"단계별 현황" 등).

**비목표 (이번 범위 밖)**
- Dagster 유지/이식 → 제거(승격지점). 새 엔진은 단일 op·CLI라 불필요.
- 컨테이너 재생성/bind-mount → 안 함(무중단 우선). docker cp + 즉시정리로.
- FiftyOne 자체 개조 → 그대로 사용.
- 개발서버 시스템 정리/이전 → 범위 밖(그건 옛 파이프라인).

## 3. 확정된 설계 결정 (LOCKED)

| 항목 | 결정 | 근거 |
|---|---|---|
| **오케스트레이션** | Dagster 제거, **경량 async 실행** | 새 엔진=단일 op·CLI. Dagster 강점 미사용 + `dagster==1.13.9`는 python<3.12 핀인데 DGX는 3.12 |
| **위치** | 관리 스택 전체 **DGX 호스트** (systemd, IP :3000) | GPU 불필요. docker exec·SQLite·크롭이 호스트에. FiftyOne 과 같은 호스트 |
| **역할** | **컨트롤 플레인**(소스·실행·모니터). 검수는 FiftyOne | 2-플레인 분리 |
| **실행 트리거** | **무중단** `docker exec vllm-shlee … label_catalog` (sh_lee docker그룹→sudo없이) | 컨테이너 재생성 안 함(수집 수십 회 예정, 라이브 무중단 우선) |
| **크롭 이동** | 런별 tmp `/engine/run_<id>` → `docker cp` 호스트 병합 → **즉시 `rm -rf` 컨테이너 tmp** | 고아 데이터 0. 컨테이너 fs 누적 방지 |
| **데이터** | 호스트 영구 `DATA_ROOT=/home/sh_lee/drheri-data`, content_hash 병합·중복제거 | 반복수집해도 안 부풂 |
| **용어** | 한국어("퍼널"→**단계별 현황**, 단계: 검출/검수대기/학습/버림) | 한국 사용자 가독성 |

## 4. 아키텍처 / 실행 흐름

```
[브라우저] ── http(IP :3000) ──► [관리 API (Starlette, 호스트)]
                                    │  SQLite(운영DB) · 정적 SPA · SSE
   수집 실행 1건:
     1) SQLite run 생성 (RUNNING)
     2) docker exec vllm-shlee  python -m drheri_pipeline.labeling.cli
            --pdf <URL|업로드파일>  --brand <B>  --pages <..>   (DATA_ROOT=/engine/run_<id>)
              └► 엔진(컨테이너): 렌더→GDINO→set-of-mark→Qwen→geom→크롭+manifest 를 /engine/run_<id> 에
     3) docker cp vllm-shlee:/engine/run_<id>/.  →  /home/sh_lee/drheri-data (content_hash 병합)
     4) docker exec vllm-shlee rm -rf /engine/run_<id>          ← 즉시 정리
     5) 호스트 후처리: manifest 읽어 fiftyone_writer 등록 + SQLite 기록 + run DONE + SSE 푸시
[FiftyOne (:5151, 호스트)] ── /home/sh_lee/drheri-data 를 읽어 검수 (keep/reject/라벨수정)
     └► keep→학습 승급 / reject→파일 즉시 삭제 (기존 review.py sync·promote 재사용)
```

GPU 작업만 컨테이너, 나머지(등록·기록·모니터·정리)는 호스트. sudo·bind-mount 없음.

## 5. 재사용 vs 신규

**그대로 재사용** (수정 최소):
- SPA 뼈대: `web/` (App·router·stores·api.js·components) + 라우트 Overview/Sources/SourceDetail/NewSource/Export/Settings
- Starlette API 뼈대: `ui/app.py`, `ui/api/{sources,runs,ops,uploads}.py`, `ui/envelope.py`, `ui/events.py`(SSE)
- 운영DB: `db/` (conn/queries/writes) — 스키마에 새 필드만 추가
- 저장·등록: `labeling/fiftyone_writer.py`, `storage.py`, 검수 승급/삭제 `review.py`(promote/sync)

**신규/재배선**:
- `ui/runner_exec.py`(신규): 경량 실행기 — run 생성 → docker exec 엔진 → cp → rm(즉시) → 등록·기록·SSE. (구 `dagster_client.py` 대체)
- `ui/api/runs.py`: "실행" 엔드포인트가 위 실행기를 async 호출(동시성 락=GPU라 1런씩 큐)
- `assets.py`/`definitions.py`/`sensors.py`/`config.py`(Dagster): **제거**
- `db/`: image 레코드에 `is_fixture`, `diameter`, `diameter_src`, `needs_review` 컬럼 추가; 단계별 현황 집계 쿼리 갱신
- SPA 표기 한국어화 + 단계 라벨(검출/검수대기/학습/버림), FunnelBar→"단계별 현황"

## 6. 데이터 모델 / 단계별 현황

크롭 라이프사이클(기존 review→training→rejected 재사용):

```
검출(detected)   →   [검수: FiftyOne]   →   학습(training)      /   버림(rejected)
 전체 크롭             is_fixture·needs_review 로 필터·정렬       keep→승급               reject→즉시삭제
```

- **검출**: GDINO 검출·크롭된 전체(구 "추출")
- **검수대기(needs_review)**: 저신뢰·필드누락·`is_fixture=False` — FiftyOne 태그로도 존재
- **학습**: 사람이 keep → training 승급 (labels.tsv export)
- **버림**: 사람이 reject → 파일·샘플 즉시 삭제
- 단계별 현황 바 = 검출 N · (검수대기 M · 픽스처의심 K) · 학습 T · 버림 R
- SQLite image 레코드: 기존 + `is_fixture`(bool) · `diameter`/`diameter_src` · `needs_review`(bool)

## 7. 소스 모델

기존 소스 등록 재사용: 브랜드 + **URL(기본)** 또는 **파일 업로드**. 엔진이 URL/파일 둘 다 받음
(`pdf_util.fetch_pdf_bytes`). 두 입력의 전달(확정):
- **URL**: `label_catalog --pdf <URL>` 그대로 — 엔진(컨테이너)이 직접 다운로드.
- **업로드 파일**: 기존 `ui/api/uploads.py`로 호스트에 저장(브랜드별) → 실행 시 그 파일을 런 tmp에
  `docker cp <host파일> vllm-shlee:/engine/run_<id>/src.pdf` 로 주입 → `label_catalog --pdf /engine/run_<id>/src.pdf`.
  런 종료 시 tmp와 함께 즉시 삭제(호스트 업로드 원본은 소스에 귀속되어 보존).

## 8. 에러 처리 / 정리 원칙

- **고아 데이터 0**: 런 tmp는 cp 직후 무조건 `rm -rf`(성공/실패 무관 finally). reject 크롭은 파일 즉시 삭제.
- 엔진 exec 실패(비정상 종료): run FAILURE 기록 + tmp 정리 + SSE(에러). 부분 크롭은 버림.
- docker exec 타임아웃(대형 카탈로그): 상한 설정, 초과 시 FAILURE + 정리.
- 동시성: GPU 공유라 **한 번에 1런**(큐). 초과 요청은 대기.
- content_hash 병합으로 재수집 안전(중복 크롭·샘플 안 생김).

## 9. 테스트 전략

- **유닛**: `runner_exec`(docker exec/cp/rm 커맨드 조립·실패시 정리 순서 — subprocess 목), run 상태전이(RUNNING→DONE/FAILURE), 단계별 현황 집계 쿼리(신 필드 포함), db 마이그레이션(새 컬럼).
- **API**: `/api/sources`·`/api/runs`(실행→run 생성·async 트리거 목)·`/api/uploads` (기존 테스트 확장).
- **SPA**: api.js·format·stores 유닛(vitest, 기존) + 한국어 라벨 스냅샷.
- **통합(호스트)**: BEGO 1건 실행 → run DONE + 크롭 호스트 병합 + 컨테이너 tmp 삭제 확인 + FiftyOne 등록 + 단계별 현황 반영.

## 10. 배치 (DGX 호스트)

- 관리 API = 호스트 venv(3.12)에 `pip install starlette uvicorn httpx python-multipart`(+ fiftyone 이미 있음), `web/dist` 빌드.
- **systemd 서비스 `drheri-ui`**(FiftyOne `fiftyone-drheri` 와 동형): `uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000`. IP 접속.
- 1회 셋업: `sudo usermod -aG docker sh_lee`(무중단, exec sudo 제거). 컨테이너 재생성 없음.
- `DATA_ROOT=/home/sh_lee/drheri-data`(호스트 영구), FiftyOne 서비스와 동일 경로.

## 11. 승격지점 (지금 안 함)

- Dagster/스케줄·백필 — 진짜 멀티스텝 DAG·정기수집 필요해지면.
- bind-mount(무재생성 유지 시 불가) — 정기 유지보수창 생기면 docker cp 제거.
- 다중 GPU 병렬 런(현재 1런 큐) — 처리량 필요 시.
- geom 로버스트니스·diameter_src FiftyOne 필드 노출 — 엔진 쪽 개선 트랙.
