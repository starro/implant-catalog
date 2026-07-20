---
name: feedback-bbox-crop-unknown
description: implant_xray bbox 좌표 해석 확정 (JS 코드로) — 다만 production 입력이 cropped fixture라 OOS bbox 평가 자체가 비활성화
metadata:
  type: feedback
---

**최종 (2026-05-30)** — bbox 좌표 의미 확정 + production 흐름 확인. **implant_xray bbox OOS 평가는 production과 무관**해 폐기.

## Production 흐름 (사용자 확인 2026-05-30)
- Dr.Heri 앱에서 사용자가 **fixture 한 장을 직접 crop해서 업로드** ("Add implant photo for comparing" UI)
- 입력 분포 = chart_implant cropped (학습 데이터)와 동일
- **in-dist top-1 87% / brand 98% = 곧 production 성능**
- panorama 자동 detection 시나리오는 없음 → bbox 풀어도 production엔 가치 없음
- 다만 bbox 해석 자체는 풀려있어 향후 panorama 전체 분석이 필요해지면 즉시 활용 가능

## bbox 좌표 정답 (JS `implantclip.drheri.js` 코드로 100% 확인)

```python
# implant_xray 4 컬럼 → panorama 픽셀 좌표
cx = ix_x * panorama_width    # W 기준 정규화 (둘 다!)
cy = ix_y * panorama_width    # !!! H가 아님
fixture_width_px = ix_w * panorama_width  # zoom factor
rotation_radians = ix_a
# fixture height는 implant.i_length / implant.i_diameter 비율로 계산
```

증거:
- JS 코드: `translate(-impl.x*width, -impl.y*width)` — x, y 둘 다 width 기준
- `rotate(impl.a + "rad")` — radian 확정
- 87.jpg의 x_tan = H/W = 0.516602 정확 일치 (panorama 비율 보조 컬럼)
- 시각 검증: 모든 fixture에 box 정확히 둘러쌈

## chart_implant 의 별도 7-컬럼 bbox 해석 (2026-06-08 추가)

위는 `implant_xray` (576 행, 4 컬럼: ix_x/y/w/a) 의 해석. 반면 학습 데이터 본체 `chart_implant` (126,587 행) 는 **7 컬럼** (`ci_x/y/a/w/h/l/e`) 사용 — 의미가 다름.

### 검증된 부분 (51806, 51807 fixture 기준, panorama 2840×1532)

| 컬럼 | 값 (51806) | 해석 | 검증 |
|------|-----------|------|------|
| `ci_w` | 0.0252316 | `× panorama_W` = crop 너비 (71px) | ✅ 실제 cropped 71×167 과 일치 |
| `ci_l` | 0.059011  | `× panorama_W` = crop **높이** (167px) | ✅ 실제 cropped 167 과 0.6px 오차 |
| `ci_a` | 6.41518   | **degree** 단위 회전 각도 (radian 아님) | ✅ 전체 분포 -60°~+28° 가 radian 으론 비현실적 |
| `ci_x` | 0.53284   | x 좌표 (정규화) — base 미확정 (W 추정) | 🟡 시각화 시 panorama 의 fixture 위치와 어긋남 → 추가 변환 필요 |
| `ci_y` | 0.376732  | y 좌표 (정규화) — base 미확정 (W or H, bottom-up?) | 🟡 H 기준 top-down 시 상악, bottom-up 시 중앙. 둘 다 어긋남 |
| `ci_h` | 0.0114379 | 미해결 (직경/두께 측정값 가능) | ❌ crop 높이 167 의 1/10 |
| `ci_e` | 0.279253  | 미해결 (eccentricity? margin?) | ❌ |

→ implant_xray 와 같은 "W 기준 정규화" 규칙 적용 시도 시 (cy = ci_y × W) 도 fixture 위치 안 맞음. **chart_implant 의 ci_x/ci_y 는 별도 origin/scale** 사용 — 추가 발굴 필요.

### 실용 권장 (재추출 시)

- 이미 우리는 chart_implant 의 학습 cropped (60,093장) 를 그대로 사용 — 재추출 불필요
- 만약 고해상도 재추출 필요하면: implant_xray 의 4 컬럼 정답 공식 (이미 풀려있음) 으로 골드셋 576장 사용
- chart_implant 의 7 컬럼은 학습 라벨 매핑용으로만 사용, bbox 픽셀 좌표 추출 안 함

## DGX 학습 데이터 흐름 (2026-06-08 확인)

**`/home/metass/data/raw/clip_implant/`** (882MB) = **NCloud `/home/drheri.data/clip_implant/` 의 byte-identical 복사**

- 51806.jpg md5: `8c4cc50ec0b41c03d2da33fbc5edfbde` — NCloud/로컬/DGX 3 곳 모두 동일
- 새로 panorama 에서 재추출 한 것 **아님** — 기존 chart_implant cropped 그대로
- `labels.tsv` (54,053 행) 가 학습 인덱스 — `brand TAB series TAB model TAB rel_path`

## OOS gap 가설 정정 (2026-06-08 production GSII X-ray 진단)

**기존 가정**: production query 의 cos 가 학습 데이터와 직교 (≈0) — domain gap 큼
**실측**: production query 의 NN raw cos = **0.87+ (강한 매치)** — 가설 완전히 정정

3-mode 비교 (사용자 GSII X-ray 한 장):

| Mode | top-1 | raw cos | 의미 |
|------|-------|---------|------|
| NN | DIO UF II 4508S | **+0.8849** | 임베딩 자체는 학습 데이터 근처 |
| Classifier (v1) | Straumann 043.230S | **-0.3879** | 🔴 head 가 production 과 반대 방향 학습 |
| Hybrid 0.7/0.3 | Straumann 043.230S | -0.0108 | classifier 가 점수 끌어내림 |

→ **진짜 문제 = ArcFace head 가 augmentation/CLAHE 없이 학습돼서 production 분포와 불일치.** 임베딩은 OK.

### 진짜 문제 — 임베딩이 GSII 와 다른 parallel-walled 시리즈 구분 못 함

NN top-10 분석:
- DIO UF II / OSSTEM TSIII SOI/CA / NEOBIOTECH EB / Astra Tech 등 모두 parallel-walled fixture
- **GSII 가 top-10 에 한 번도 안 나옴** (학습 189장 있는데)
- 50-200px / ~10KB 저해상도 cropped 에서 brand/series 미세 차이 학습 불가

→ Brand 정확도 84.3% 양호, **OSSTEM 까진 잘 잡지만 GSII vs USIII SA 구분 실패**.

## CLAHE + augmentation 효과 (2026-06-08 측정)

| 단계 | val_acc1 | val_acc5 | classifier raw cos (GSII query) | top-1 |
|------|---------|---------|---------------------------------|-------|
| v1 baseline (random split) | 45.1% | 80.2% | -0.39 (broken) | Straumann |
| v2 honest (stratified) | 43.51% | 75.00% | -0.39 | Straumann |
| **v2_aug** (augmentation features 257K) | **46.97%** | **80.36%** | +0.20 (정상화) | Straumann |
| **v2_aug + query CLAHE** (serve 단) | 46.97% (학습 동일) | 80.36% | **+0.20 (정상)** | **OSSTEM USIII SA** ✅ |

→ **CLAHE 적용 + v2_aug head 가 classifier 정상화 시킴**. 사용자 query 와 학습 분포 매치. ArcFace head 가 broken → 정상.

→ **OSSTEM USIII SA top-1** (GSII 의 형제 시리즈, 외형 매우 유사). Brand 정답, series 까진 학습 데이터 한계.

## DGX `search_image_v2` 의 구조 (2026-06-08 분석)

- `arcface_topk`: `cos = v @ af_weight.T` (둘 다 normalized), 범위 [-1, 1]
- `nn_topk`: Qdrant `Cosine` collection, score 0 ~ 1 (자기매치 1.0)
- `hybrid` 모드: `score = α·af_score + (1-α)·nn_score` — α 가 production 성능에 결정적
  - **0.7 (default)** → classifier broken 시 점수 망가짐
  - **0.1 (2026-06-08 적용)** → classifier broken 영향 최소화
- 출력 `ct` 필드 = raw cos 값 (변환 없음)
- frontend (`index.vue`) 가 화면 표시 시 `(ct + 1).toFixed(4)` 변환 → [0, 2] 범위

## ⚠️ Frontend filter bug 발견 + 수정 (2026-06-08)

`c:/projects/implant-ai-web/app/pages/index.vue` 의 visibleResults filter 가 **거꾸로 적용**되어 있었음:

```js
// BUG: (ct + 1) <= 1 즉 ct <= 0 만 표시 → 양수 cos (좋은 매치) 모두 가려짐
const visibleResults = computed(() => (result.value?.data || []).filter(d => ((d.ct ?? 0) + 1) <= 1))

// FIX: filter 제거 (DGX top-K 그대로 신뢰)
const visibleResults = computed(() => result.value?.data || [])
```

→ classifier 가 broken 이던 시절 raw cos 가 -0.4 라서 화면 통과는 됐음. fix 후 양수 cos 도 통과.

## 진행 중 작업 (2026-06-08 세션 끝)

| 작업 | 상태 |
|------|------|
| CLAHE features 재추출 (학습 데이터에도 적용, 257K) | 진행 중 (~105분) |
| 추출 끝나면 v2_aug_clahe 학습 (자동 chain) | 대기 |
| serve 자동 재시작 (v2_aug_clahe + CLAHE) | 대기 |
| `04_finetune_dinov2_partial.py` — DINOv2 last 4 blocks unfreeze + head 함께 학습 | 스크립트 준비됨, 미실행 |
| NCloud panorama 에서 고해상도 재추출 (chart_implant ci_l × W 검증됨) | 미시작 (큰 작업) |

## 다음 세션 권장 순서

1. **v2_aug_clahe 결과 확인** — query 와 학습 양쪽 CLAHE 일치 후 top-1 변화
2. **DINOv2 partial fine-tune (v3_ft)** — backbone 미세 특징 학습. EPOCHS=15 추정 2-4시간
3. **GSII 추가 데이터 수집** — 현재 189장, GS2M3513R01 2장. NCloud panorama 활용
4. **OSSTEM 전용 sub-classifier** — brand 후 series 결정 단계 분리

## 2026-06-10 ~ 06-17 후속 작업 — v3_ft / v4_mt / v5_bal

### v3_ft (DINOv2 partial fine-tune, 2026-06-10)
- DINOv2-giant 마지막 4 transformer blocks unfreeze (113M / 1.13B = 10% trainable) + ArcFace head 함께 학습
- 학습 데이터: chart_implant cropped + CLAHE preprocessing
- 학습 시간: 5시간 7분 (DGX Spark GB10), 15 epoch
- 결과: **val_acc1 65.62% (+18.7%p from v2_aug)**, val_acc5 92.61%
- 체크포인트: `~/models/fixture_v3_ft/ft_best.pt` (2.28GB, backbone+head 통합)
- search_image_v2.py 에 `backbone_state` 로딩 코드 추가 — 기존 head-only 체크포인트와 하위 호환

### v4_mt (Multi-task spec ontology, 2026-06-16)
- 동기: in-dist val_acc 65% 가 holistic classification 의 한계. GSII vs USIII SA 등 형제 시리즈 구분 못함. 임상의가 X-ray 식별 시 보는 단서 (coronal/middle/apical 3구간의 thread design, microthread, size) 를 모델이 명시적으로 학습 안 함.
- 추가 head 9개: c_micro / c_surface / m_shape / m_surface / a_shape / a_hole / a_groove (분류) + diameter / length (회귀)
- spec 라벨 source: `implant_spec.tsv` (25,110 rows). labels.tsv 와 productcode join 으로 95.3% cover.
- 학습 시간: 5시간 14분
- 결과:
  - val_acc1 65.60% (v3_ft 와 동일 — main classification plateau 확인)
  - **micro acc 96.2%** (microthread Y/N 정확 학습)
  - **diameter MAE 0.19mm** (Mini/Regular/Wide 정확 구분)
- 체크포인트: `~/models/fixture_v4_mt/mt_best.pt`, `aux_state` 추가
- search_image_v2.py 에 `MultiTaskHeads` 클래스 + `decode_aux` 함수 추가. 응답에 `spec_prediction` 필드 포함:
  ```json
  "spec_prediction": {
    "c_micro": {"label": "N", "p": 0.47},
    "m_shape": {"label": "Tapered", "p": 0.40},
    "a_groove": {"label": "Y", "p": 0.60},
    "diameter_mm": 0.33,  // ⚠️ inference 버그 (학습 시 MAE 0.19, inference 시 0.x mm 출력)
    "length_mm": 0.53
  }
  ```
- ⚠️ diameter/length regression inference 버그: 학습 시 MAE 0.19mm 정상인데 inference 시 0.x mm 출력. dtype 또는 head weight 로딩 의심. **미해결**.

### v4_mt 결정적 발견 — modality gap + brand prior bias

X-ray (학습 sample) 로 query 시: Nobel Biocare 정답 → top-3 에 Nobel 3개 (raw cos +0.72).
**광학 매크로 사진** (실물) 로 query 시: Nobel 정답 → top-10 모두 OSSTEM, raw cos +0.07 (random).

→ 두 가지 동시 원인:
1. **Modality gap**: 학습 데이터 100% X-ray cropped, 광학 사진 0장 → DINOv2 일반 prior 만 작동, fine-tuned prototype 과 거리 큼.
2. **Brand prior bias**: OSSTEM 16,400장 vs Nobel 2,221장 (7배). 분류기 head 가 OSSTEM 으로 강하게 기울어짐.

**spec_prediction 은 정확** (micro=N, m_shape=Tapered, a_groove=Y → NobelSpeedy/Replace 패턴). 즉 **임베딩은 Nobel-like 인식, 분류기 head 만 OSSTEM 으로 답** — 진단 명확.

### v5_bal (Class-balanced retrain, 2026-06-17, 진행 중)
- 변경: `WeightedRandomSampler(1/sqrt(brand_count))` 추가. Nobel sample weight = OSSTEM × 2.72배.
- 나머지는 v4_mt 와 동일
- ep1 결과 (학습 진행 중):
  - val_acc1 52.33% (head class 양보)
  - val_brand_acc 87.91%
  - **🚀 Nobel top-5 = 97.2%** (이전 v4_mt 추정 30%)
  - GSII top-5 = 84.2% (v3_ft 73.7%)
- 평가: 단 1 epoch 만에 long-tail brand recall 폭발적 향상. balanced sampling 효과 명확 확인.

### 인프라 변경 누적
| 변경 | 일자 | 비고 |
|------|------|------|
| Frontend `(ct+1)<=1` filter 제거 | 06-08 | 양수 cos 가리던 버그 ([feedback_implant_ai_ct_filter_bug.md](feedback_implant_ai_ct_filter_bug.md)) |
| Mode toggle UI (Hybrid/Classifier/NN) | 06-08 | `index.vue` |
| Hybrid weight 0.7+0.3 → 0.1+0.9 | 06-08 | classifier broken 보호 (v2_aug 당시), v5_bal 후 재조정 검토 |
| DGX SSH password 인증 활성화 | 06-10 | PuTTY 지원, [reference_dgx_ssh.md](reference_dgx_ssh.md) |
| DGX IP 변경 192.168.0.132 → 192.168.0.27 | 06-15 | DHCP 갱신. SSH config + Spring Boot yaml + README 갱신 |
| `application.yaml` dgx.base-url | 06-15 | DGX IP 변경 따라 |
| spec_prediction UI 카드 추가 | 06-17 | `index.vue` 결과 위에 표시 |

### 다음 세션 (학습 완료 후) 작업
1. v5_bal 학습 완료 (~5시간) → serve 자동 재시작 (auto chain PID 166608)
2. Nobel 광학 사진 재테스트 — v5_bal 의 brand 균형 효과 확인
3. **diameter/length regression inference 버그 수정** — `decode_aux` 의 dtype 또는 weight 로딩 검증
4. Hybrid weight 재조정 (classifier 가 정상화됐으므로 0.5+0.5 또는 다시 0.7+0.3)
5. Qdrant collection 재인덱싱 — v3_ft/v4_mt/v5_bal 의 새 backbone 으로 학습 데이터 re-embed → NN mode 회복
6. 메모리 inferences 결과 정리 (panorama 재추출 검토)

## 사용 시 주의 — Domain Gap

bbox 좌표는 풀었지만 cropped fixture로 OOS 평가하면 in-dist 87% → OOS 0-3% 폭락 (2026-05-30 측정).

원인 (추정):
- 학습 데이터(chart_implant cropped)와 panorama crop이 cropping 스타일·후처리·contrast 다름
- 학습 데이터에 sharpening / CLAHE / 다른 augmentation 적용 가능성
- 학습 데이터의 cropping 도구 자체가 우리 PIL crop과 다른 알고리즘

해결 후속 작업:
1. **D1.5 augmentation 재시도** (1-2h) — random crop/rotate/contrast/blur
2. **OOS preprocessing pipeline** — CLAHE / sharpening / dynamic range 표준화
3. **chart_implant cropping 코드 발굴** — implant_cut.drheri.js 등 어떤 후처리?
4. **Domain adaptation** — 학습-OOS feature alignment (fine-tune with mixed)

**How to apply:** bbox 좌표는 그대로 사용 가능. OOS 평가가 필요할 땐 위 후속 작업 후. 현재 in-dist 87% top-1은 유효 (production 사용 가능).

[[project-drheri-implant-ai]] [[reference-drheri-implant-db]] 참조.

**Why:** 2026-05-30 시도한 가정 (`ix_x, ix_y = 정규화 center 좌표 0~1` / `ix_w = panorama width 비율` / `ix_a = radian/degree 회전` / `aspect ratio 3:1`)으로 crop 후 시각 검증 결과, hold-out 248.jpg가 빈 회색 영역으로 나옴 (같은 모델 학습 이미지와 비교 시 명백히 다름). 그 결과 zero-shot 평가에서 top-1 2%로 매우 낮음. 그러나 같은 시스템·임베딩으로 **chart_implant 자체 in-distribution 평가는 top-1 42%/brand 85%** — 즉 시스템은 healthy, 평가 데이터(crop)만 문제.

**How to apply:**
- implant_xray 골드셋 평가 (576 검수 데이터) 사용 전 **bbox 해석 재검증 필수**
- 검증 방법:
  1. chart_implant의 `ci_*` (x, y, a, w, h, l, e 7개)와 implant_xray의 `ix_*` (4개) 매핑 추적
  2. 한 implant에 대해 chart_implant + implant_xray 양쪽 bbox 있으면 비교
  3. 시각 검증 (한 장 crop 결과를 같은 모델 학습 이미지와 비교)
- 검증 안 된 상태라면 **chart_implant에서 hold-out 격리** (이미 cropped라 crop 문제 0)하는 in-distribution 평가만 사용
- 검수 골드셋(implant_xray) 평가는 외부 OOS 검증에 가치 큰 자산 — 해석 풀리면 즉시 활용
- 현재 cropped 결과 (`~/data/benchmark/holdout_v1/cropped/`)는 **신뢰하지 말 것**, 재crop 후 재평가

가능한 재해석 가설 (시도해볼 것):
- ix_w가 width 아니라 height/length일 수도 → aspect 1/3으로 시도
- ix_a 단위가 radian이 아니라 다른 (예: x_tan 컬럼처럼 tangent 값)
- ix_x, ix_y가 center가 아니라 top-left 또는 fixture 시작점
- 좌표가 정규화 0~1이 아니라 다른 기준 (예: x_tan 1.0 기준 mm)
- 또는 ix_x/ix_y/ix_w/ix_a가 affine transform 행렬 일부 (예: rotated rectangle의 두 점)

[[project-drheri-implant-ai]] [[reference-drheri-implant-db]] 참조. 내일 D3 작업 항목.
