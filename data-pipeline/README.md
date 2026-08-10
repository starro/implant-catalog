# drheri-pipeline

Dr.HERi 임플란트 이미지 **수집·라벨링 파이프라인**. 설계 청사진 → [`../design/data-pipeline-architecture.md`](../design/data-pipeline-architecture.md).

여러 원천(URL 사이트·카탈로그 PDF·수집 이미지)에서 임플란트 X-ray/카탈로그 이미지를 모아
`brand/series/model/{xray,catalog}` 계층으로 정리하고, 사람 검수(FiftyOne)를 거쳐
학습 데이터셋(+ provenance 매니페스트)을 만든다.

## 단계

```
소스 → (raw) → review → training
              👁 FiftyOne 검수      manifest.jsonl(출처) + labels.tsv(DGX export)
```
단계 수는 소스 타입이 결정 (raw·review는 옵션). 매트릭스는 설계 문서 §5.

## 셋업 (uv)

```bash
uv venv --python 3.11
uv pip install -e .
cp .env.example .env
# DocLayout-YOLO 첫 사용 시 HF 모델 자동 다운로드
```

## 실행

```bash
# Dagster UI (자산/잡 확인 + Launchpad로 URL 입력)
bash scripts/dev.sh            # http://localhost:3333

# FiftyOne 검수 (review 단계 이미지)
# (검수 스크립트는 추후)
```

## 두 가지 수집 경로 (Job)

| Job | 소스 | 흐름 | URL 입력 |
|-----|------|------|---------|
| `ingest_site_xray` | whatimplantisthat API (Osstem) | review → training | Launchpad: `api_url`, `company_filter` |
| `ingest_catalog_pdf` | 오스템 카탈로그 PDF URL | raw → review → training | Launchpad: `pdf_url` |

데모 시 `auto_approve: true` (기본) 면 검수 게이트를 건너뛰고 training 까지 자동 완주.
실제 운용에선 `auto_approve: false` 로 두고 FiftyOne 검수 후 승급.

## 구조

```
drheri_pipeline/
├── definitions.py     # Dagster Definitions (assets + jobs)
├── config.py          # Config 클래스 (Launchpad 입력 스키마)
├── storage.py         # 경로/해시/매니페스트(jsonl) + labels.tsv export
├── normalize.py       # 시리즈명 정규화 (전각 파이프 등)
├── review.py          # FiftyOne 등록 + review→training 승급
└── sources/
    ├── site_xray.py   # whatimplantisthat API 수집
    └── catalog_pdf.py # PDF 다운로드 + DocLayout-YOLO 추출
```

## 재설계 UI 배포 절차

Jinja2 템플릿(`ui/templates/index.html`) · `ui/registry.py` · `scripts/promote_reviewed.*` 를
제거하고 Svelte SPA 정적 서빙(`web/dist`)으로 전환했다. `drheri_pipeline/ui/app.py::create_app()` 가
`/api/*` 는 기존 라우트 그대로, `/` 이하는 `web/dist` 를 정적으로 서빙한다(빌드 전이면 안내 JSON 을 반환).

개발서버(58.229.105.3, `jay8126`)에 반영할 때는 순서대로 실행한다.

```bash
cd ~/Dr.HERi/data-pipeline
git pull

# 1) 백필 — 먼저 백업
cp data/manifest.jsonl data/manifest.jsonl.bak
cp data/sources.jsonl data/sources.jsonl.bak
.venv/bin/python -m scripts.backfill_db

# 2) 화면 빌드
cd web && npm install && npm run build && cd ..

# 3) saved view 생성 (문서별 doc-<id> 뷰 + 버림 전용 뷰)
FIFTYONE_DATABASE_VALIDATION=false .venv/bin/python -m scripts.fiftyone_saved_views

# 4) 서비스 재기동 (root: su -)
su - -c "bash /home/jay8126/Dr.HERi/data-pipeline/scripts/setup_ui_root.sh"
su - -c "systemctl restart catalog-ui"
```

검증:

```bash
curl -s http://127.0.0.1:3000/api/health
curl -s http://127.0.0.1:3000/api/sources | head -c 400
```

기대값: 첫 명령이 `{"ok": true, "data": {"db": true, ...}}`, 두 번째가 백필된 브랜드·문서 트리.

브라우저에서 `http://58.229.105.3:3000` 을 열어 아래를 확인한다.

1. 소스 목록에 브랜드 › 문서와 퍼널이 보이는가
2. 문서 상세에서 `수집 실행` → 완료 시 **새로고침 없이** 토스트가 뜨고 퍼널이 갱신되는가
3. FiftyOne 에서 태그를 찍고 `검수결과 반영` 을 누르면 학습/버림 숫자가 바뀌는가
4. 재기동 후 `pgrep -af "[f]iftyone" | wc -l` 이 1인가

> 참고: `scripts/setup_ui_root.sh` / `scripts/setup_systemd_root.sh` 의 배포 경로 변수(`H`)는
> 스크립트 자신의 위치에서 자동으로 유도된다(`$(dirname "$0")/..`) — 위 예시처럼 저장소 안의
> 실제 경로(`/home/jay8126/Dr.HERi/data-pipeline/scripts/...`)로 실행하면 별도 설정이 필요 없다.
> 저장소를 다른 경로에 클론했거나 스크립트를 복사해서 실행하는 경우에는
> `H=/other/path bash setup_ui_root.sh` 처럼 환경변수로 덮어쓸 수 있다.

> 위 절차는 Windows 로컬 개발 환경에서는 실행하지 않았다(개발서버 접속 정보 없음) — 문서화만 해 둔다.
