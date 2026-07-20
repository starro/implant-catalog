---
name: project-implant-ai
description: "implant-ai 신규 프로젝트 — 임플란트 픽스처 사진 식별, Spring Boot 프록시 + Nuxt 프론트, DGX ML 추론 연동"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4e62b605-c331-47c8-aa57-db879c30cb9f
---

Dr.Heri 임플란트 픽스처(fixture) 식별 시스템. 사용자가 임플란트 사진을 업로드하면 DGX ML 추론 서버가 유사도 순으로 매칭 제품을 반환. 2026-05-30 신규 생성, 아직 **git 저장소 아님** (로컬만 존재).

**구성 2개 레포** (`c:\projects\`):
- `implant-ai-api` — Java 21 / Spring Boot 3.5.8 / Gradle. 무상태 프록시. DGX(`http://192.168.0.132:8080`)의 `/search_image_v2`로 이미지 검색 위임 + catalog/training 이미지 정적 서빙. 포트 **8081**. 엔드포인트 `/api/implant/*` (search hybrid/classifier/nn, health, training 샘플). `application.yaml`에 `data/catalog`, `data/training` 디렉토리 필요. 시크릿 없음. `./gradlew bootRun`.
- `implant-ai-web` — Nuxt 4.2 / Vue 3 / Quasar v2 (ko-KR), SSR off SPA. 포트 **3000**. `NUXT_PUBLIC_API_URL`(기본 `http://localhost:8081`)로 API 연결. `yarn install && yarn dev`. Node ≥22.

둘 다 기능 완성도 높음(프로토타입 아님), 테스트 코드는 없음. DGX는 [[project-dgx-dataset-baseline]]의 qwen SFT용 DGX와 동일 장비일 가능성(사내 192.168.x) — 단 용도는 별개(여긴 이미지 임베딩/arcface 분류).

주의: git 미초기화 상태 — 개발 본격화 전 저장소 초기화/원격 등록 여부 확인 필요.
