# Dr.HERi Implant Fixture Identification — 공유 문서

Dr.HERi 임플란트 픽스처 자동 식별 시스템 (implant-ai) 의 설계/학습/디버깅 history.

작성: 2026-06-17
최종 업데이트: 2026-06-17 (v5_bal 학습 진행 중)

---

## 폴더 구성

| 파일 | 내용 |
|------|------|
| **README.md** | 이 파일 — 인덱스, 빠른 시작, 시스템 현황 |
| `01_project_overview.md` | implant-ai 프로젝트 개요 (web + api + DGX 구조) |
| `02_dgx_setup.md` | DGX Spark 접속/네트워크/SSH 설정 |
| `03_implant_db_schema.md` | NCloud Dr.HERi DB 스키마 + 학습 데이터 통계 |
| `04_training_history.md` | v1 → v2_aug → v3_ft → v4_mt → v5_bal 학습 history (가장 중요) |
| `05_known_bugs_and_fixes.md` | 알려진 버그 + 수정 내역 (frontend filter, regression 등) |

---

## 시스템 현황 (2026-06-17)

### 배포된 컴포넌트

```
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│  Nuxt 4 + Quasar v2  │   │  Spring Boot 3.5     │   │   DGX Spark GB10     │
│  implant-ai-web      │──▶│  implant-ai-api      │──▶│  search_image_v2     │
│  :3000               │   │  :8081 (proxy)       │   │  :8080  (FastAPI)    │
└──────────────────────┘   └──────────────────────┘   └──────────────────────┘
                                                                │
                                                       ┌────────┴─────────┐
                                                       │  Qdrant fixture_v1│
                                                       │  :6333  (NN mode) │
                                                       └───────────────────┘
```

### 현재 운영 모델

| 모델 | val_acc1 | 비고 |
|------|---------|------|
| **v3_ft** (DINOv2 partial fine-tune) | 65.62% | 첫 본격 backbone fine-tune. 5시간 학습 |
| **v4_mt** (Multi-task spec ontology) | 65.60% | + microthread / size 등 spec 학습. spec_prediction API 응답 |
| **v5_bal** (Class-balanced sampling) | **진행 중** (ep1: Nobel top-5 97.2%) | long-tail brand 회복용 |

### 학습 데이터

- chart_implant cropped X-ray: **54,053장** (882MB)
- 713 unique brand|series|model classes
- 8 brand 학습 cover (OSSTEM/Dentsply/Straumann/NEOBIOTECH/DIO/Nobel/DENTIUM/Point)
- spec ontology coverage: **95.3%** (51,523 / 54,053)

---

## 빠른 시작

### DGX 접속

```bash
ssh dgx     # ~/.ssh/config 의 alias 사용 (key 또는 password)
# 직접: ssh -i ~/.ssh/id_ed25519_dgx metass@192.168.0.27
```

자세한 내용 → [02_dgx_setup.md](02_dgx_setup.md)

### Serve 재시작 (모델 변경 시)

```bash
ssh dgx 'pkill -f "uvicorn search_image_v2" ; sleep 3 ; nohup bash -c "source ~/work/ai/bin/activate; cd ~/scripts/serve; ARCFACE_CKPT=~/models/<모델명>/<ckpt>.pt HF_HOME=~/models/hf_cache uvicorn search_image_v2:app --host 0.0.0.0 --port 8080" > ~/logs/serve.log 2>&1 &'
```

모델 선택:
- 안정 운영: `~/models/fixture_v3_ft/ft_best.pt`
- Spec 정보 응답 필요: `~/models/fixture_v4_mt/mt_best.pt`
- (예정) long-tail 균등: `~/models/fixture_v5_bal/bal_best.pt`

### 로컬 서버 띄우기

```powershell
# Spring Boot (port 8081)
cd c:/projects/implant-ai-api
./gradlew.bat bootRun

# Nuxt (port 3000)
cd c:/projects/implant-ai-web
yarn dev
```

### Health 확인

```bash
curl http://localhost:8081/api/implant/health   # 로컬 → DGX 통합 헬스
curl http://192.168.0.27:8080/health             # DGX 직접
```

---

## 핵심 발견 요약

### 1. Frontend `(ct+1) <= 1` filter 버그 (2026-06-08)
양수 cosine (좋은 매치) 가 화면에서 가려져 있던 버그. classifier 가 broken (raw cos -0.4) 이던 시절엔 음수 cos 가 통과돼서 안 터졌고, 모델 개선 (CLAHE/augmentation) 으로 양수 cos 가 나오자 결과 사라짐. → filter 제거.

### 2. ArcFace head broken in production (2026-06-08)
v2/v2_aug 까지: classifier raw cos -0.39 (반대 방향). augmentation + CLAHE 학습 일치로 +0.20 로 정상화. v3_ft 의 backbone fine-tune 후 +0.50.

### 3. OOS modality gap (2026-06-16~17)
**광학 매크로 사진 query 는 학습 X-ray 와 본질적으로 다른 modality.** 학습 데이터 100% X-ray cropped, 광학 사진 0장 → DINOv2 일반 prior 만 작동, fine-tuned prototype 과 거리 큼. raw cos 0.07 (random) 으로 떨어짐.

같은 fixture 의 X-ray 로 query 시: top-3 에 정답 brand 진입, raw cos 0.7+.

### 4. Brand prior bias (2026-06-17)
학습 데이터 brand 별 7배 차이 (OSSTEM 16K vs Nobel 2K) 로 분류기가 OSSTEM 으로 강하게 기울어짐. **spec_prediction (multi-task) 은 정확** — 임베딩은 brand 구분 가능, 분류기 head 만 bias. → class-balanced sampling (v5_bal) 으로 해결.

### 5. 학습 데이터 해상도 한계
chart_implant cropped: 50-200px / ~10KB. NCloud panorama 원본: 2840×1532 / ~1.2MB (370배 픽셀). bbox 좌표 일부 풀려있어 (`ci_w·W = width`, `ci_l·W = height`, `ci_a = degree`) panorama 재추출 가능. **미실행**.

자세한 history → [04_training_history.md](04_training_history.md)

---

## 알려진 버그 / 미해결

| 버그 | 상태 | 우선순위 |
|------|------|--------|
| v4_mt diameter/length regression inference 0.x mm 출력 (학습 시 MAE 0.19mm 정상) | 🔴 미해결 | 중 |
| Qdrant collection 옛 backbone embedding — v3+ backbone 변경 후 NN mode raw cos 0.11 로 폭락 | 🔴 미해결 | 중 |
| 광학 사진 modality gap — 학습 데이터에 광학 사진 0장 | 🟡 기록 | 낮음 (수집 비용 큼) |

자세한 내용 → [05_known_bugs_and_fixes.md](05_known_bugs_and_fixes.md)

---

## 변경 이력

- **2026-06-17**: v5_bal class-balanced 학습 시작. README 작성, 공유 폴더 정리.
- **2026-06-16**: v4_mt 학습 완료 + spec_prediction UI 카드 추가.
- **2026-06-15**: DGX IP 192.168.0.132 → 192.168.0.27 (DHCP 갱신). SSH config + Spring Boot yaml 갱신.
- **2026-06-10**: v3_ft (DINOv2 partial fine-tune) 학습 완료. backbone_state 로딩 코드 추가. SSH password 인증 활성화.
- **2026-06-08**: Frontend filter 버그 수정. 3-mode UI toggle 추가. v2_aug + CLAHE serve 가동.
- **2026-05-30**: implant_xray bbox 좌표 해석 완료 (JS 코드 분석). in-dist top-1 87% 측정.

작성자에게 문의: mazineta99@gmail.com
