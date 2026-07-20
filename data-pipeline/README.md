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
