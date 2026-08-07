# DGX 카탈로그 자동 라벨링 엔진

- 작성일: 2026-08-07
- 상태: 설계 승인 대기
- 대상: DGX(sh_lee) 신규 파이프라인 — 카탈로그 PDF → 픽스처 검출·크롭 → VLM 스펙 매핑 → FiftyOne 미리라벨 검수
- 관련 메모리: `project_dgx_catalog_labeling_pipeline`

## 1. 배경과 문제

임플란트 픽스처를 **제조사(brand) / 상세 모델(model) / 직경(diameter) / 길이(length)** 로 분류하는
학습셋을 만든다. 소스는 제조사 카탈로그 PDF다. 길이는 이미지 픽셀로 측정할 수 없으므로(카탈로그
렌더에 스케일 없음) **PDF 텍스트·part number** 에서 얻는다.

핵심 아이디어: 사람이 크롭을 하나하나 라벨링하는 대신, **AI 가 미리 라벨을 달아둔 크롭**을 FiftyOne 에
띄우고 사람은 **확인·수정·keep/reject** 만 한다. AI 는 두 축으로 나뉜다 — 픽스처가 **어디**(WHERE)
있는지는 Grounding DINO, 그 픽스처가 **무엇**(WHAT)인지는 Qwen3-VL.

두 축 모두 DGX(GB10)에서 2026-08-07 실측 검증됨: Grounding DINO 픽스처 5/5 검출(0.35s/page),
Qwen3-VL-8B-Instruct 정확 추출(웜 10.6s/page).

## 2. 목표 / 비목표

**목표**
- 카탈로그 PDF 한 건을 받아 픽스처를 검출·크롭하고, 각 크롭에 brand/model/diameter(+가능하면
  length·part_number)를 **미리 채운** 라벨로 FiftyOne 샘플을 생성한다.
- 사람은 FiftyOne 에서 라벨을 확인·수정하고 keep/reject 한다. keep 을 학습셋으로 export 한다.
- **기본적으로 빠르다** — 성능이 1급 요구사항이다(§7).
- 입력은 URL 수집이 기본, NAS 파일 직접 읽기가 대체 경로. 엔진은 "PDF 하나"만 받는다.

**비목표 (이번 범위 밖)**
- 관리 UI / 퍼널 대시보드 / Dagster 오케스트레이션 재구축 → 승격지점(§11).
- 브랜드별 레이아웃 프로필 하드코딩 → VLM 이 일반화하므로 v1 불필요.
- 32B 모델 에스컬레이션 → 어려운 페이지용, 나중.
- length 를 이미지 픽셀로 측정하는 것(불가능, §6 참조).
- 개발서버에 무엇이든 남기는 것(§4에서 DGX 통합으로 확정).

## 3. 확정된 설계 결정 (LOCKED)

| 항목 | 결정 | 근거 |
|---|---|---|
| **배치** | **DGX 완전 통합.** 개발서버엔 아무것도 안 남김 | 네트워크 한 방향(개발서버→DGX 172.30.1.x 도달불가) + 입력(NAS)·연산(GPU)·소비자(metass 학습) 전부 DGX 쪽. 내부 서비스라 외부노출 불요 → split 이유 소멸 |
| **검수 substrate** | Mongo + FiftyOne 을 DGX 에 올림 | docker run / pip. mongo AVX 이슈는 x86 전용이라 ARM GB10 엔 무관 |
| **입력** | URL 다운로드 **또는** NAS 파일. 하나의 PDF 소스 추상화 | 기존 `catalog_pdf` 가 URL/로컬 둘 다 받던 방식 계승. **DGX 는 NAS 직접 마운트 가능** → 개발서버가 쓰던 브라우저 업로드 우회 불필요 |
| **검출** | Grounding DINO, **시각적 프롬프트** `"a gray implant object"`, threshold≈0.3 | 의미적 프롬프트("dental implant")는 1-2/5, 시각적 묘사는 5/5 검출 |
| **매핑** | **하이브리드 set-of-mark**: 페이지에 번호 박스 오버레이 → Qwen 1콜로 박스별 스펙. 항목수 불일치/저confidence 페이지만 박스별 개별콜로 재시도 | 레이아웃이 브랜드마다 제각각(내부는 일관)이라 기하 순서 가정 불가 → VLM grounding 에 위임. 1콜/page 로 빠르게, 애매할 때만 정밀 |
| **저장** | 크롭·라벨·FiftyOne·학습셋 = DGX 로컬(`/` 3.3T). NAS = 읽기전용 입력 | 크롭 로컬이라 FiftyOne filepath 제약 자동 해결, 왕복 제로 |
| **오케스트레이션** | v1 = CLI + 실행원장(content_hash 멱등) | Dagster 는 옛 추출에 배선됨. 볼륨 커지면 승격 |

## 4. 아키텍처 / 데이터 흐름

```
카탈로그 PDF  (URL 다운로드  또는  //172.30.1.8/nas-metass 파일)
  → 페이지 렌더 (PDF→PNG): 고해상도 마스터 1회 + 읽기용 다운스케일 뷰 (§7)
  → [페이지 필터] Grounding DINO(다운스케일 뷰) 박스 0개면 스킵  ← 느린 VLM 낭비 차단
  → 픽스처 있는 페이지마다 (여러 페이지 병렬):
       Grounding DINO(다운스케일 뷰) → 픽스처 박스 N개  → 좌표를 마스터 스케일로 환산
       다운스케일 뷰에 박스를 번호로 오버레이 (set-of-mark)
       Qwen3-VL(vLLM :8000) 1콜 → 박스별 {model, diameter, length?, part_number?, confidence, evidence}
         └ 항목수≠박스수 또는 저confidence → 그 페이지만 박스별 개별콜 재시도
       length = part_number 파싱 우선, 없으면 VLM 이 읽은 값
       박스 크롭을 **고해상도 마스터에서** 떠서 DGX 로컬 저장  ← 학습 데이터 품질
       FiftyOne 샘플 생성 (미리라벨 + confidence + 출처, 낮으면 needs_review 태그)
  → 실행 원장(JSON/작은 SQLite): pdf·페이지·건수, content_hash 중복제거
사람 → DGX FiftyOne: 라벨 확인·수정, keep/reject
  → keep export → 학습셋(DGX 로컬, metass 소비)
```

## 5. 구성 단위 (각각 독립·테스트 가능)

| 단위 | 역할 | 입력 → 출력 |
|---|---|---|
| `source_resolver` | URL/파일 → 로컬 PDF 경로 | `str(url\|path)` → `Path` |
| `page_renderer` | PDF → 고해상도 마스터 + 다운스케일 뷰(스케일 계수 보존) | `(pdf_path, master_dpi, view_px)` → `list[PageImage{master, view, scale}]` |
| `detector` | Grounding DINO 래퍼(모델 1회 로드 재사용, 다운스케일 뷰 입력) | `PageImage.view` → `list[Box]` (score, xyxy@master) |
| `mapper` | Qwen3-VL vLLM 클라이언트(set-of-mark 프롬프트 + 파싱) | `(PageImage, list[Box])` → `list[BoxSpec]` |
| `partnum_parser` | part_number → length·검증 (순수함수, 브랜드별 확장) | `(brand, part_number)` → `length?` |
| `fiftyone_writer` | 크롭 + 라벨 → FiftyOne 샘플(스키마 §6, review 플래그) | `list[LabeledCrop]` → 샘플 |
| `ledger` | 실행 기록·중복제거·진행 | content_hash |
| `runner` (CLI) | PDF/브랜드 단위 오케스트레이션, 페이지 병렬 | `label_catalog --pdf X --brand Y --pages 12-26` |

각 단위는 인터페이스로만 소통한다. `detector`/`mapper` 는 검증된 실측 코드를 감싼다(§9 참고값).

## 6. FiftyOne 라벨 스키마

샘플 = 크롭 1장. 필드:

| 필드 | 타입 | 비고 |
|---|---|---|
| `brand` | Classification | 소스 브랜드에서 결정(입력 시 이미 앎) |
| `model` | Classification | VLM |
| `diameter` | Classification | VLM |
| `length` | Classification\|list | **아래 라벨 granularity 규칙 참조** |
| `part_number` | 문자열\|list | VLM/파싱 |
| `ai_confidence` | float | 매핑 신뢰도 |
| `evidence` | 문자열 | VLM 이 인용한 근거 텍스트(검수 보조) |
| `source_pdf`,`source_page`,`box` | 메타 | 재현·역추적 |
| 태그 `needs_review` | — | confidence 낮거나 필드 비면 |

**라벨 granularity 규칙(중요)**: 라벨은 **크롭이 시각적으로 구별하는 수준**까지만 단정한다.
카탈로그가 한 직경을 렌더 하나로 표현하고 그 안에 여러 길이 SKU 가 있으면, 그 크롭은 시각적으로
brand+model+diameter 까지만 담는다(길이는 catalog 스케일에서 동일). 이때 `length` 는 단일값으로
강제하지 않고 **해당 렌더가 공유하는 길이 집합/part_number 목록을 메타로** 둔다. 길이가 렌더별로
유일하게 결정될 때만 단일 라벨. → "같은 이미지를 여러 길이로 복제" 금지.

## 7. 성능 요구사항 (1급)

"기본적으로 무조건 빠르다"를 구체 레버로:

1. **페이지 필터(최대 승부처)**: GDINO(0.35s)로 먼저 훑어 **박스 0개 페이지는 VLM 호출 안 함**.
   146p 카탈로그에서 스펙 20p면 VLM(10.6s)을 20회만 — 126회 절감.
2. **동시성**: vLLM 은 동시 요청을 배치 처리한다. 페이지 VLM 콜을 병렬로 던져 순차 `10.6s×N` 을
   벽시계상 대폭 단축. 병렬도는 GPU 메모리 여유(현 `--gpu-memory-utilization 0.35`) 내에서 조절.
3. **모델 상시 웜**: 콜드 리로드 금지(예전 100s+ 지연의 주범). vLLM 컨테이너 상주(`--restart
   unless-stopped`), GDINO 모델 프로세스 내 1회 로드 후 재사용.
4. **해상도 이원화(속도 ↔ 품질 분리)**:
   - **읽기·검출용 다운스케일 뷰** — VLM/GDINO 입력. 글자 읽힐 최소 해상도로(이미지 토큰 ∝ 해상도).
     검증에 쓴 768/1024px 기준으로 가독-속도 균형점 확정. 속도는 여기서 번다.
   - **크롭용 고해상도 마스터** — 페이지를 높은 DPI 로 1회 렌더해 보관. **크롭은 이 마스터에서** 뜬다.
     박스 좌표는 뷰→마스터 스케일 계수로 환산. 크롭은 학습 데이터이므로 **해상도를 충분히 높게**
     유지한다(다운스케일 뷰에서 크롭 뜨는 것 금지).
5. **1콜/page 기본**, 박스별 개별콜은 드문 애매 페이지로 한정.

목표: 카탈로그 1건을 (수동 라벨링 대비) 분 단위로 미리라벨. 회귀 방지로 처리시간을 원장에 기록.
(주: 마스터 렌더는 크롭 품질용이라 속도 예산 밖 — 페이지당 1회 렌더 비용만 든다.)

## 8. 에러 처리

- 페이지 렌더 실패 → 스킵 + 로그(전체 중단 안 함).
- 검출 0개 → 페이지 스킵(정상 경로).
- VLM 파싱 실패/타임아웃 → 크래시 대신 `needs_review` 샘플 생성(사람이 처리).
- 개별콜 재시도도 실패 → 박스는 라벨 비운 채 등록 + `needs_review`.
- 원장 멱등: content_hash 로 재수집해도 중복 크롭·샘플 안 생김.
- NAS 마운트 끊김 → 명확한 에러로 조기 실패(부분 처리 금지).

## 9. 테스트 전략

- **유닛**: `partnum_parser`(순수함수, 브랜드별 케이스), `mapper` 프롬프트조립·응답파싱(vLLM 목),
  `detector` 후처리(픽스처 이미지 픽스처로 박스 개수/좌표), `fiftyone_writer` 스키마·플래그, `ledger`
  멱등·중복제거.
- **통합**: BEGO-2018.pdf p18 (검증된 5픽스처 페이지) end-to-end → 기대 크롭 수·라벨 필드 존재·
  needs_review 규칙. 실측 참고값: GDINO 박스 5개(score 0.51–0.53), Qwen 정확 추출.
- **비회귀**: 처리시간 상한(웜 기준 페이지당·카탈로그당) 기록·경보.

검증된 호출 규약(구현 시 그대로 사용):
- vLLM: `POST 127.0.0.1:8000/v1/chat/completions`, model `qwen3vl`, content=[text, image_url(data:image/png;base64)], temp 0.
- GDINO: `IDEA-Research/grounding-dino-base`, transformers 4.57 `post_process_grounded_object_detection(threshold=…, text_threshold=…)`(주의: `box_threshold` 아님), 라벨은 `text_labels`.

## 10. 실행 위치 · 인프라

- **DGX sh_lee.** 돌고 있는 vLLM 컨테이너(`vllm-shlee`, :8000) + GDINO(같은 컨테이너 transformers) 재사용.
- **신규**: DGX 에 Mongo + FiftyOne(ARM 이미지/휠). metass·qdrant 무간섭(별 계정·별 포트).
- **NAS** `//172.30.1.8/nas-metass` 를 DGX 에 **읽기전용 CIFS 마운트**(카탈로그 경로
  `03. Dr.HERi/02. 카탈로그/<브랜드>/*.pdf`, ~31 브랜드). 마운트 인증정보는 구현 시 사용자에게 수령.
- 산출물 루트: DGX 로컬 `data/`(크롭·라벨·원장·학습셋). NAS 엔 쓰지 않음.

## 11. 승격지점 (지금 안 하지만 자리 남김)

- 관리 UI(소스등록·퍼널·실행버튼): 껍데기 재사용, 새 엔진에 배선. 볼륨 커지면.
- Dagster 오케스트레이션: CLI→스케줄러 승격 시.
- 브랜드별 part_number 검증기(내부 일관성 활용한 QA).
- 32B 에스컬레이션: 저confidence 페이지 재처리.
