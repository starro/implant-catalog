# Dr.HERi — Implant Fixture Identification (implant-ai)

임플란트 픽스처(fixture) 자동 식별 시스템. 사용자가 임플란트 사진(주로 X-ray cropped)을 업로드하면
DGX ML 추론 서버가 임베딩 유사도 기반으로 매칭 제품(brand/series/model)을 반환한다.

> 이 루트(`C:\dev\Dr.HERi`)는 **내 담당 영역 = 데이터 수집/라벨링 파이프라인**의 작업 기반이다.
> 시스템 전체(웹/API/DGX 학습/DB)는 다른 작업자 영역이며 아래 "참조 컨텍스트"로만 둔다.
> 상세 history·DB 스키마·학습 기록은 [md_files/implant-ai/](md_files/implant-ai/) (다른 작업자 문서).

---

## 🎯 내 담당 영역 — 데이터 수집/라벨링 파이프라인

implant-ai의 **상류(upstream)**: 임플란트 카탈로그/X-ray 이미지를 여러 경로(웹·PDF)에서 수집 →
출처 추적 + **제조사 → 브랜드 → 시대** 계층 라벨링 → 체계적 디렉토리로 정리 → **학습 데이터셋 공급**.
이게 하류 DGX ML 학습(v3_ft/v4_mt/v5_bal)의 입력을 만든다.

- **PoC 기반**: `c:/dev/image-origin-poc` (Dagster + FiftyOne). heri2go·Dr.HERi와 별개 레포.
- **계획**: 2026-06-22 주부터 로컬 PoC를 바탕으로 **리눅스 서버에 재구성**.
- **검증된 기법** (리눅스로 이식):
  - PDF 추출 2방식 — PyMuPDF 객체추출(`extract_image`) + DocLayout-YOLO figure 검출(벡터 포함). 보완관계.
  - jpx(JPEG2000) → **PIL 디코딩→PNG 재인코딩**(Pixmap 직접 변환 금지, 이미지 뭉갬).
  - `nearby_text`(PyMuPDF `get_textbox`, OCR 불필요) → 모델코드 후보 힌트(자동라벨 X, 검수용).
  - FiftyOne 큐레이션 — `stage` 필드로 가공전(raw, PDF는 샘플 X)/중간처리/학습용 분리.
- **하류 연동(다음 가치지점)**: DGX `search_image_v2`(:8080) / Qdrant `fixture_v1` 을 호출해
  수집 이미지의 **노이즈 필터 + 브랜드 라벨 제안**에 활용 (미구현).
- **장기 비전**: Dagster·FiftyOne·자체 UI를 하나의 통합 웹서비스로 묶기 — 각 엔진을 API/GraphQL로 호출하는 구조.

> 아래부터는 전부 **참조 컨텍스트** (다른 작업자 영역 / 상·하류 시스템). 내가 직접 수정하는 대상 아님.

---

## [참조] 시스템 구성

```
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│  Nuxt 4 + Quasar v2  │   │  Spring Boot 3.5     │   │   DGX Spark GB10     │
│  implant-ai-web      │──▶│  implant-ai-api      │──▶│  search_image_v2     │
│  :3000  (SPA, ko-KR) │   │  :8081  (무상태 프록시)│   │  :8080  (FastAPI)    │
└──────────────────────┘   └──────────────────────┘   └──────────┬───────────┘
                                                       ┌──────────┴───────────┐
                                                       │  Qdrant  fixture_v1   │
                                                       │  :6333   (NN mode)    │
                                                       └───────────────────────┘
```

| 레이어 | 역할 | 기술 | 포트 |
|--------|------|------|------|
| **implant-ai-web** | 프론트엔드 (이미지 업로드, 결과 표시) | Nuxt 4.2 / Vue 3 / Quasar v2, SSR off SPA, Node ≥22 | 3000 |
| **implant-ai-api** | 무상태 프록시 + catalog/training 이미지 정적 서빙 | Java 21 / Spring Boot 3.5.8 / Gradle | 8081 |
| **DGX search_image_v2** | 이미지 임베딩 + ArcFace 분류 + NN 검색 | FastAPI, DINOv2-giant + ArcFace head | 8080 |
| **Qdrant fixture_v1** | 벡터 NN 검색 (Cosine) | Qdrant | 6333 |

### 코드 레포 위치 — ⚠️ 참조 전용 (이 로컬에 없음)

`implant-ai-web`(Nuxt) + `implant-ai-api`(Spring Boot 프록시)는 **다른 작업자**가 만든 컴포넌트로,
**이 로컬 PC에는 구성되어 있지 않다.** 아키텍처 이해를 위한 참조로만 둔다 (수정 대상 아님).

내가(이 PC 담당자) 작업하는 영역은 위 두 레포와 **다른 영역** — 아래 "내 담당 영역" 참조.

---

## [참조] 다른 작업자 컴포넌트 실행 (이 로컬엔 없음)

```powershell
# Spring Boot 프록시 (port 8081) — 다른 작업자 레포
cd c:/projects/implant-ai-api ; ./gradlew.bat bootRun
# Nuxt 웹 (port 3000) — 다른 작업자 레포
cd c:/projects/implant-ai-web ; yarn dev
```
Health: `curl http://localhost:8081/api/implant/health` / `curl http://192.168.0.27:8080/health`

### DGX 접속 (내 파이프라인이 호출하는 도구)
```bash
ssh dgx     # ~/.ssh/config alias (전용 키 id_ed25519_dgx). 상세 → md_files/implant-ai/02_dgx_setup.md
```

### Serve 재시작 (모델 변경 시)
```bash
ssh dgx 'pkill -f "uvicorn search_image_v2" ; sleep 3 ; nohup bash -c \
  "source ~/work/ai/bin/activate; cd ~/scripts/serve; \
   ARCFACE_CKPT=~/models/<모델명>/<ckpt>.pt HF_HOME=~/models/hf_cache \
   uvicorn search_image_v2:app --host 0.0.0.0 --port 8080" > ~/logs/serve.log 2>&1 &'
```
모델 선택: 안정 `fixture_v3_ft/ft_best.pt` · spec 응답 `fixture_v4_mt/mt_best.pt` · long-tail 균등 `fixture_v5_bal/bal_best.pt`

---

## 인프라 식별자

| 대상 | 값 | 비고 |
|------|-----|------|
| DGX Spark (aitopatom-c681) | `192.168.0.27` (유선 LAN) | DHCP — 변경 이력 .132→.27. 계정 `metass`, 키 `~/.ssh/id_ed25519_dgx` |
| NCloud DB 서버 (drheri-op-web-api-2) | 내부 `10.36.6.102` (VPN) / 공인 `118.67.132.58` (data.drheri.com) | CentOS 7.8, MariaDB 5.5.68, DB `drhericom` |

⚠️ **비밀번호·평문 크리덴셜은 이 저장소/메모리에 절대 저장 금지.** DGX/DB 패스워드는 사용자 로컬에만.

---

## [참조] 학습 데이터 자산 (내 파이프라인이 보강·공급하는 대상)

- **chart_implant cropped X-ray**: 54,053장 (882MB), 713 unique `brand|series|model` 클래스
- 8개 brand 학습 cover: OSSTEM / Dentsply / Straumann / NEOBIOTECH / DIO / Nobel / DENTIUM / Point
- spec ontology coverage 95.3% (51,523 / 54,053)
- 입력 분포 = 사용자가 직접 crop 업로드한 fixture (= 학습 데이터와 동일 modality, in-dist top-1 ~87%)
- DB 스키마·테이블·long-tail 분포 상세 → [md_files/implant-ai/03_implant_db_schema.md](md_files/implant-ai/03_implant_db_schema.md)

### spec ontology (12차원) 호환 주의
신규 AI의 attribute 출력 enum 은 기존 DB 컬럼(`i_pc_type`, `i_c_micro` 등) 값과 **반드시 일치**해야 백엔드 호환.
재정의 금지. 매핑표 → 03_implant_db_schema.md.

---

## [참조] 학습 모델 현황 (하류 DGX ML — 다른 작업자/공동)

| 모델 | val_acc1 | 핵심 | 체크포인트 |
|------|---------|------|-----------|
| v3_ft (DINOv2 partial fine-tune) | 65.62% | 첫 backbone fine-tune (5h) | `~/models/fixture_v3_ft/ft_best.pt` |
| v4_mt (Multi-task spec ontology) | 65.60% | + spec 9-head (micro/shape/size). `spec_prediction` 응답 | `~/models/fixture_v4_mt/mt_best.pt` |
| v5_bal (Class-balanced sampling) | 진행 중 | long-tail brand recall 회복 (Nobel top-5 97.2%) | `~/models/fixture_v5_bal/bal_best.pt` |

상세 학습 history (CLAHE·augmentation·modality gap·brand bias) → [md_files/implant-ai/04_training_history.md](md_files/implant-ai/04_training_history.md)

### 핵심 발견 (반드시 인지)
1. **ArcFace head 부호**: serve 의 `ct` = raw cosine [-1,1]. frontend 표시 = `(ct+1)` 변환([0,2], 1.0=random). 두 layer 분리해 다룰 것.
2. **OOS modality gap**: 학습 100% X-ray cropped, 광학 매크로 사진 0장 → 광학 query 시 raw cos 0.07(random). X-ray query 는 0.7+.
3. **Brand prior bias**: OSSTEM 16K vs Nobel 2K (7배) → 분류기 head 가 OSSTEM 편향. 임베딩은 정상. → v5_bal class-balanced 로 해결.

---

## [참조] 알려진 버그 / 미해결 (하류 시스템)

| 버그 | 상태 | 우선순위 |
|------|------|--------|
| v4_mt diameter/length regression inference 0.x mm 출력 (학습 MAE 0.19mm 정상) | 🔴 미해결 | 중 |
| Qdrant fixture_v1 가 옛 backbone embedding — v3+ backbone 변경 후 NN mode raw cos 0.11 폭락. 재인덱싱 필요 | 🔴 미해결 | 중 |
| 광학 사진 modality gap (학습 데이터 광학 0장) | 🟡 기록 | 낮음 (수집 비용 큼) |

상세 + frontend `(ct+1)<=1` filter 버그 history → [md_files/implant-ai/05_known_bugs_and_fixes.md](md_files/implant-ai/05_known_bugs_and_fixes.md)

---

## 작업 규칙 (내 영역 = 데이터 파이프라인)

- **시크릿**: DGX/DB SSH 패스워드·DB 크리덴셜을 코드/문서/메모리에 커밋 금지. 값은 로컬에만 (`.env` gitignore).
- **이미지 modality**: 수집·라벨링 시 X-ray vs 광학(카탈로그) modality를 항상 구분·기록. 하류 학습이 modality gap에 민감.
- **라벨 enum 호환**: 제조사/브랜드/spec 라벨은 기존 DB enum(`md_files/.../03`)과 일치시켜 하류 호환 유지. 임의 재정의 금지.
- **PoC 기법 준수**: jpx→PIL→PNG 정규화, PDF 2방식 추출, FiftyOne 큐레이션 후 전체 재빌드 금지(태그 보존) — 상세는 image-origin-poc 메모리.
- **하류 연동**: DGX `search_image_v2` 응답 `ct`는 raw cosine([-1,1], 1.0이 아닌 0이 random 기준)임에 유의. 라벨 제안에 쓸 때 부호·임계값 분리 검토.

> 하류(Spring Boot/Nuxt) 규칙 — `Instant` 사용, 엔드포인트 GET/POST 만, drop-in 응답 포맷(ii/bi/pn/...) — 은
> 다른 작업자 영역이라 여기선 참조만. 상세는 `md_files/implant-ai/`.
