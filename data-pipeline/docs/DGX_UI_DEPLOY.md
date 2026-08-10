# DGX 관리 UI · 라벨링 엔진 배포/운영 가이드

Dr.HERi 카탈로그 라벨링 시스템을 DGX(GB10, 172.30.1.6, 계정 `sh_lee`)에 올리고 운영하는 방법.
2계층: **호스트 제어면**(관리 UI + FiftyOne) + **컨테이너 엔진**(vLLM + Grounding DINO).

## 구성 요소

| 계층 | 무엇 | 위치 |
|---|---|---|
| 제어면 | 관리 UI (Starlette + SPA) | systemd `catalog-ui.service` → `foenv/bin/uvicorn drheri_pipeline.ui.app:app :3000` |
| 제어면 | FiftyOne App (검수) | systemd `fiftyone-drheri.service` → `foenv/bin/python serve_dgx.py :5151` |
| 엔진 | vLLM (Qwen3-VL-8B) | 컨테이너 `vllm-shlee` :8000 |
| 엔진 | Grounding DINO HTTP | 컨테이너 `vllm-shlee` :8100 (`python /engine/gdino_server.py`) |

- 호스트 venv: **`/home/sh_lee/foenv`** (uvicorn, fiftyone, pypdf 등)
- 호스트 코드: **`/home/sh_lee/engine/`** (`drheri_pipeline/`, `scripts/`, `web/dist/`, `gdino_server.py`)
- 데이터: **`DATA_ROOT=/home/sh_lee/drheri-data`** (SQLite `pipeline.db`, `review/` `training/` `rejected/`, `manifest.jsonl`)
- 컨테이너 엔진 코드: **`/engine/`** (호스트에서 `docker cp` 로 주입 — 호스트 `engine/` 와 별개)

## 배포 (코드 변경 반영)

배포 때 **반드시 함께 올려야 하는 4곳** (하나라도 빠지면 런타임 오류):

1. **`drheri_pipeline/` 패키지** → `pscp` → `/home/sh_lee/engine/drheri_pipeline/...`
2. **`scripts/` 패키지** → `/home/sh_lee/engine/scripts/...`
   - `sync.py` 가 `scripts.fiftyone_saved_views` 를 import 한다. 빠지면 **검수결과 반영이 500**.
3. **`web/dist/`** (SPA 빌드) → 기존 dist 삭제 후 `pscp -r` → `/home/sh_lee/engine/web/dist/`
   - 로컬 빌드: `cd web && npm run build`. 하드 새로고침(Ctrl+Shift+R)으로 새 JS 로드.
4. **`gdino_server.py`** (엔진 검출 서버) → 호스트로 `pscp` 후 **컨테이너로 `docker cp`**:
   `docker cp /home/sh_lee/engine/gdino_server.py vllm-shlee:/engine/gdino_server.py`

반영:
- 제어면(`drheri_pipeline`, `scripts`, `dist`) → `sudo systemctl restart catalog-ui`
- 엔진(`gdino_server.py`) → GDINO 프로세스 재시작(아래 "복구 플레이북")

## NAS (카탈로그 원본 PDF)

원본 PDF는 NAS(SMB)에 있고 DGX 호스트에 **읽기전용 CIFS** 마운트한다.

- 공유 `//172.30.1.8/NAS-METASS`, 마운트 `/mnt/nas` (ro), 계정 `nas-user01`(비번은 `/etc/cifs-nas-metass.cred`, root:600)
- 카탈로그 루트: `NAS_CATALOG_ROOT=/mnt/nas/03. Dr.HERi/02. 카탈로그/<브랜드>/*.pdf`
- `/etc/fstab` 에 `nofail,_netdev` 항목 등록 → 재부팅 유지
- 수집 흐름: UI 에서 NAS 파일 선택 → `url`=호스트 절대경로 → 수집 시 `_prepare_pdf` 가 `docker cp` 로 컨테이너 주입(업로드와 동일). 컨테이너엔 NAS 바인드 없음.

## 엔진 켜기/끄기 (GPU 양보)

수집 안 할 땐 엔진을 내려 GPU(~44GB)를 다른 계정(metass) 학습에 양보. UI 헤더에서 조작하거나:
- `docker start vllm-shlee` + `docker exec -d vllm-shlee bash -lc 'python /engine/gdino_server.py > /tmp/gdino.log 2>&1'`
- `docker stop vllm-shlee`

`engine.status()` = `down`|`starting`|`ready`. `ready` 는 vLLM + **GDINO `/health`(실추론)** 통과 시.

## 복구 플레이북 — GDINO cuDNN 오염

**증상:** 수집이 크롭 0으로 실패 + `docker cp ... run_N/. not found` + `/tmp/gdino.log` 에
`RuntimeError: ... unable to find an engine to execute this computation`. cuDNN conv 엔진을
못 잡는 GPU 컨텍스트 오염. 한 번 나면 프로세스 재시작 전까지 이후 detect 전부 전염.

**자동:** `gdino_server` 가 detect/health 실패 시 `empty_cache` 재시도 → 모델 재로드 재시도로
자가복구. 복구 실패면 `/health` 503 → `engine.status`=`starting` → UI가 수집 차단.

**수동(자가복구도 안 될 때):**
```bash
docker exec vllm-shlee bash -lc 'pkill -f gdino_server.py; sleep 2'
docker exec -d vllm-shlee bash -lc 'python /engine/gdino_server.py > /tmp/gdino.log 2>&1'
# ~15초 후: docker exec vllm-shlee curl -s http://127.0.0.1:8100/health  → {"ok":true}
```
그래도 안 되면 `docker restart vllm-shlee`(vLLM까지 재로드 ~40초) 또는 GPU 메모리 경합 해소.

## 검수(FiftyOne) 판정

- 샘플 태그 **`keep`** / **`reject`** 로 판정 후 UI 헤더 **"검수결과 반영"** 클릭.
- `reject` → `data/rejected/` 이동 + FiftyOne 에서 제거(재태깅 복구 불가).
- `keep` + brand/series/model 완비 → training 승급.
- saved view: 문서별 `doc-<id>`("이 문서만 보기") + `rejected`. `scripts.fiftyone_saved_views` 가 갱신.
- **App 세션은 launch 시점 ds 스냅샷** — 이후 다른 프로세스가 만든 saved view 를 모른다.
  serve 스크립트가 20초 주기 `ds.reload()` 로 재기동 없이 최신화(그래서 수집 직후 doc-N 이 안 걸리면 ~20초 기다리면 됨). 없으면 fiftyone-drheri 재시작이 유일한 해법이 된다.

## 시간 감각 (실측)

수집 비용은 **페이지 수 × 페이지당 이미지 수**(VLM set-of-mark). 페이지당 ~18–20초.
예: ADIN 35p→177크롭 7.5분 / Alpha-Bio 67p→581크롭 26.6분 / Bicon-MAX 24p→232크롭 9.4분.
