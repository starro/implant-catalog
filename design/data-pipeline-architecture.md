# 데이터 수집·라벨링 파이프라인 설계

> Dr.HERi(implant-ai) **상류 데이터 파이프라인**의 아키텍처 청사진.
> 담당: 데이터 수집/라벨링 (웹/API/DGX 학습은 다른 작업자 영역 — 참조).
> 현재 = 설계 단계(코드 없음). 차주(2026-06-22 주~) 로컬 PoC를 바탕으로 **리눅스 서버 재구성**의 기준 문서.
> 작성 2026-06-22.

---

## 0. 목적

여러 원천(URL 사이트·PDF·수집 이미지·로컬 업로드)에서 임플란트 **카탈로그 + X-ray 이미지**를 반복 수집하고,
**출처(오리진)를 추적**하면서 **제조사 → 시리즈 → 모델** 계층으로 라벨링해, 하류 DGX ML 학습이 쓸
**정규화된 학습 데이터셋 + 매니페스트**를 만든다.

---

## 1. 핵심 원칙 (확정)

1. **사람도 이미지를 본다** — 중간 검수(FiftyOne)가 설계의 중심축. 자동화는 사람 검수를 *돕는* 것이지 대체하지 않는다.
2. **디렉토리 = 사람용 / 매니페스트 = 모델용** — 물리 트리는 사람·큐레이션을 위한 것이고, 학습 라벨의 *유일 출처(source of truth)*는 정규화된 매니페스트다. (모델은 경로를 보지 않는다)
3. **브랜드는 모든 단계를 관통하는 안정 축**, 추출·검수로 비로소 드러나는 건 series/model.
4. **단계 수는 소스 타입이 결정한다** — raw·중간(review)은 *옵션*이며, 추출이 필요한 소스(카탈로그 PDF)만 풀 단계를 거친다. (§5 매트릭스)
5. **오리진은 끝까지 따라간다** — 모든 이미지가 source_id/URL/페이지·bbox 까지 provenance를 보존해 매니페스트에 싣는다.

---

## 2. 레이어 개요

```
[소스 레지스트리]  ← 내가 직접 관리하는 대상 (어디서 가져오는가)
      │
      ├─(추출 필요: 카탈로그 PDF)─▶  raw/  ─▶  review/  ─▶  training/  + manifest
      │
      └─(추출 불필요: 사이트·수집이미지·X-ray)──────▶  review/  ─▶  training/  + manifest
                                                   (또는 X-ray는 review도 건너뛰고 바로 training)
```

- **raw** = 추출 전 원본(PDF 등). 사람이 직접 보기 어려움 → FiftyOne 미표시, provenance 메타로만.
- **review (중간단계)** = 추출/수집된 개별 이미지 + *잠정* 라벨. 👁 FiftyOne로 사람이 keep/reject·라벨수정.
- **training (학습데이터)** = 사람이 승인한 이미지 + *확정* 메타. 디렉토리 + 매니페스트.

---

## 3. 디렉토리 체계

```
data/
├── sources/                                  # 소스 레지스트리 (§4) — 메타/설정
│
├── raw/        <brand>/<source>/<file>.pdf    # 추출 전. brand 확정(취득 시 앎), series/model 미상
│                                              #   └ 추출 필요 소스만 존재
│
├── review/     <brand>/<series>/<model>/{xray,catalog}/<hash>.<ext>
│                                              # 잠정 라벨. 👁 FiftyOne 검수 대상
│                                              #   series/model 미정이면 _unknown
│
└── training/   <brand>/<series>/<model>/{xray,catalog}/<hash>.<ext>
              manifest.jsonl                   # 작업 메타 = 유일 출처(provenance·bbox·옵션필드 native)
              labels.tsv                       # ↑를 평탄화한 DGX 학습 인덱스(export, brand/series/model/rel_path)
```

- `{xray,catalog}` = modality, **leaf 레벨**. (방안 B)
- 파일명 = `content_hash`(중복 제거·provenance 키). 원본 파일명은 메타로 보존.
- raw는 brand 까지만, review/training 부터 series/model/modality.

---

## 4. 소스 레이어 (오리진 관리)

내가 직접 관리하는 "어디서 가져오는가"의 레지스트리.

| 소스 타입 | 예 | 브랜드 판별 | modality | 수집 도구 |
|----------|-----|-----------|----------|----------|
| **URL-사이트 (다중 브랜드)** | spotimplant.com, osseosource.com | 사이트 구조로 **항목별** | 사이트가 xray/catalog 구분 | Playwright/Chromium |
| **URL-PDF (단일 브랜드)** | 오스템 카탈로그 PDF URL | 소스 통째 **확정** | catalog | HTTP 다운로드 |
| **수집된 이미지 파일** | 이미 모아둔 디렉토리 | 일부만 | 섞임 | 파일시스템 스캔 |
| **로컬 업로드** | 직접 올리는 파일 | 올릴 때 지정 | 지정 | 폴더 감시 |
| **기타/출처 미상** | — | ❌ → `_unknown` | ❌ | 사람 검수 |

### 브랜드 "선언 지점" 3모드 (PoC 라벨 추출기 레지스트리 재사용)
1. **declared** — 폴더 배치 자체가 라벨 (`raw/DIO/...` = brand:DIO). 단일 브랜드 PDF.
2. **structured-site** — 사이트가 제품별 브랜드/모달리티를 자기 데이터로 제공 → 수집 중 항목별 해석. (PoC whatimplantisthat 패턴)
3. **manual** — 출처 미상 → `_unknown`, FiftyOne 검수에서 사람이 채움.

### 소스 레코드(예시 필드)
`id, type(url_site|url_pdf|image_batch|local_upload), url|path, brand(known|multi|unknown), modality(xray|catalog|mixed|unknown), brand_resolution(declared|structured|manual), fetched_at, notes`

---

## 5. 단계 건너뛰기 매트릭스 ⭐

**소스 타입이 거치는 단계를 결정한다.** raw·review는 필수가 아니다.

| 소스 타입 | raw | review | training | 비고 |
|----------|:---:|:---:|:---:|------|
| 카탈로그 PDF (단일브랜드) | ✅ | ✅ | ✅ | **유일하게 풀 파이프라인** (DocLayout 추출) |
| 다중브랜드 사이트 | ⛔ | ✅ | ✅ | 이미 개별 이미지 → 추출 불필요, 검수만 |
| 수집된 이미지 파일 | ⛔ | ✅ | ✅ | 검수만 |
| 로컬 업로드 | ⛔ | 선택 | ✅ | 라벨 확실하면 review 생략 가능 |
| **X-ray (이미 crop됨)** | ⛔ | ⛔/선택 | ✅ | 바로 학습 (raw·중간 불필요 — 사용자 확인) |

→ 설계상 raw·review 단계는 **존재할 수도, 없을 수도** 있는 옵션 노드. Dagster가 소스 타입으로 분기.

---

## 6. 도구 매핑

| 도구 | 담당 | 역할 |
|------|------|------|
| **Dagster** | 전체 | 오케스트레이션. 소스 레지스트리 읽어 타입별 라우팅, 단계 분기, 사람 검수 게이트 전후 연결, 정규화·매니페스트 생성. 브랜드 = 파티션 키 후보 |
| **DocLayout-YOLO** (+PyMuPDF) | raw→review | PDF 페이지 figure 검출·crop + nearby_text. **카탈로그 PDF 경로에서만** |
| **Playwright/Chromium** | 소스→(review) | URL-사이트 크롤링, 항목별 brand/modality 수집 |
| **FiftyOne** | review (+training 열람) | 👁 사람 검수 UI. keep/reject, brand/series/model/modality 라벨 수정. raw(PDF) 미표시 |

---

## 7. 사람 검수 게이트 (review → training)

자동화가 사람에게 넘어가는 유일한 지점. FiftyOne ↔ Dagster 핸드셰이크:

1. Dagster가 review 이미지 생성 → FiftyOne 데이터셋 등록 (`stage=review`, 잠정 라벨/nearby_text 힌트 포함)
2. 사람이 FiftyOne에서 keep/reject + series/model/modality 수정
3. Dagster **승급 자산**이 FiftyOne 태그/필드를 다시 읽어 → keep 된 것만 **정규화 적용** → training/ 이동 + manifest 행 추가

> ⚠️ FiftyOne 큐레이션 시작 후에는 데이터셋 **전체 재빌드 금지**(태그 소실). content_hash 기준 증분 add + 메타만 갱신.

---

## 8. 정규화 규칙 (승급 시 1회 적용)

- **시리즈명 정규화** — 전각 파이프 `｜` 주변 공백·문자 차이로 디렉토리/라벨이 중복 분리되는 것 방지.
  (DGX 실측 사례: `NobelActive TiUltra｜WP` vs `... ｜ WP` 두 개로 갈림)
- brand/series/model 표기는 **DGX `labels.tsv` 및 DB enum 과 일치**시켜 하류 병합·호환 유지. 임의 재정의 금지.
- modality는 `{xray, catalog}` 고정값.

---

## 9. Provenance / 매니페스트 (2단 구성, 확정)

메타데이터는 **2단(two-tier)**으로 둔다. 오리진 사슬 `source → raw → review → training` 전 구간 보존.

```
working manifest  →  manifest.jsonl   (유일 출처 / source of truth)
        │  정제·정규화 후 평탄화 export
        ▼
DGX 학습 인덱스   →  labels.tsv        (산출물 / DGX 호환)
```

### 설계 원칙 — JSONL = DGX taxonomy 를 **포함하는 superset**
우리는 풍부한 JSONL(유일 출처)만 잘 채운다. DGX taxonomy(brand/series/model)는 그 **부분집합**.
TSV 는 우리 책임이 아니라 **언제든 뽑히는 산출물**(DGX 가 가져갈 때 만들든, 우리가 export 하든).
**DGX 라벨 품질은 신뢰 대상 아님** — 우리가 수용하는 건 *taxonomy(유효 이름 사전)* 이지 그들의 개별 라벨 판단이 아님. 라벨은 우리가 독립적으로 단다.

**라벨은 원자 단위로 분해 저장** (DGX 는 surface 를 series 에 합쳐 쓰지만 — `TSIII SA` — 우리는 따로):
- `series="TSIII"`, `surface="SA"` → export 시 `compose_series` 로 `"TSIII SA"` (DGX 호환)
- `series="GSII"`, `surface=null` → `"GSII"`
- 브랜드는 export 시 `normalize_brand` 로 DGX 표기(`Osstem→OSSTEM IMPLANT`)

### ① `manifest.jsonl` — 라벨링 스키마 (유일 출처, superset)
한 줄 = 한 이미지(JSON 객체). 없는 필드는 생략 가능(JSONL 유연).
```jsonc
{
  "content_hash":"...", "path":"...", "stage":"review|training", "status":"...",
  // ── DGX taxonomy 핵심 (export → tsv) ──
  "brand":"Osstem", "series":"TSIII", "surface":"SA", "model":"TS3R4011",
  "modality":"xray|catalog",
  // ── 우리 확장 (DGX엔 없어도 됨) ──
  "era":null, "spec":{"diameter":null,"length":null,"microthread":null},
  "region_parts":null, "notes":null,
  // ── provenance + 라벨 메타 ──
  "source_id":"...", "source_type":"url_pdf", "origin_url":"...#page=14",
  "page_no":14, "bbox":[..], "label_method":"human|accepted_suggestion",
  "suggested_series":"TSIII", "fetched_at":"..."
}
```
- **brand/series/surface/model** = DGX 가 가져갈 부분(교집합). **era/spec/region_parts/notes** = 우리 확장.
- 검수 중 라벨 변경 = append-only 로그로 쌓고 `latest_by_hash` 가 최신만 채택.

### ② `labels.tsv` — DGX export (산출물)
`storage.export_labels_tsv()`: training 승인분을 `brand ⇥ series ⇥ model ⇥ rel_path` 로.
- 브랜드 `normalize_brand`, series `compose_series(series, surface)`. UTF-8, 헤더 1행, 셀 내 TAB/개행 금지.
- taxonomy 정렬은 `drheri_pipeline/taxonomy.py` (BRAND_ALIASES, compose_series).

→ JSONL = 풍부한 라벨/추적/검수(superset), TSV = DGX 가 먹는 평면 라벨(교집합 투영). 역추적 항상 가능.

---

## 10. PoC에서 이미 검증된 조각 (리눅스로 이식)

- PDF 추출 2방식 (PyMuPDF 객체 + DocLayout-YOLO figure, 보완관계)
- jpx(JPEG2000) → PIL 디코딩→PNG 재인코딩 (Pixmap 직접변환 금지)
- nearby_text (PyMuPDF get_textbox, OCR 불필요) → 모델코드 후보 힌트(자동라벨 X)
- FiftyOne stage 필드로 중간처리/학습용 분리 표시
- 라벨 추출기 레지스트리 (declared / structured-site / generic fallback)

리눅스 이점: 윈도우 python 스텁/경로/jpx 호환 이슈 제거 + GPU 가속(DocLayout-YOLO).

---

## 11. 열린 결정사항 (TBD)

1. ~~매니페스트 형식~~ → **2단 확정** (2026-06-22): 작업메타 `manifest.jsonl`(출처) + DGX export `labels.tsv`. §9.
2. **승급 트리거** — 검수 후 Dagster 수동 실행 vs FiftyOne 태그 감지 센서 자동.
3. **잠정 라벨 자동화 깊이** — nearby_text 힌트를 어디까지 자동 적용하고 어디부터 사람에게 맡길지.
4. **modality 판정 granularity** — 소스 단위 선언으로 충분한지, 항목별 필요 케이스.
5. **하류 연동** — DGX search_image_v2 / Qdrant fixture_v1 으로 노이즈 필터·브랜드 라벨 제안(다음 가치지점, 미구현).
6. ~~레포 위치~~ → **Dr.HERi 하위 신규 레포 확정** (2026-06-22): `C:\dev\Dr.HERi\data-pipeline\` (패키지 `drheri_pipeline`). PoC(image-origin-poc) 자산은 재사용·이식만.

---

## 12. 구현 노트 (2026-06-22 착수)

- **레포**: `C:\dev\Dr.HERi\data-pipeline\`, 패키지 `drheri_pipeline`, uv venv, Dagster 1.13.9.
- **URL 입력 = Dagster typed `Config`** — Launchpad에서 URL 입력 후 Materialize. (확장: 소스 레지스트리 파일 + dynamic partitions)
- **Job A (site_xray)**: whatimplantisthat **API 직접**(`/api/implants/all`) — 이미지 URL이 레코드 `images[].url` 에 포함되어 **Playwright 불필요**. company_name 필터(Osstem), `images[].meta` radioimg→xray. brand=declared, series=record.name(정규화), model=파일명 stem.
- **Job B (catalog_pdf)**: pdf_url 다운로드 → raw → DocLayout-YOLO+PyMuPDF 추출 → review(catalog).
- **auto_approve** config 플래그: 데모용으로 검수 게이트 건너뛰고 training 까지 자동 완주 검증.
