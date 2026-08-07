# 페이지 범위 입력 + 수집 초기화

- 작성일: 2026-07-21
- 상태: 설계 승인됨
- 대상: `data-pipeline`

## 배경

- 페이지 입력이 콤마 목록만 받아 `12-26`을 넣으면 `int("12-26")` 에러로 수집이 실패한다. 대용량 카탈로그(예: BEGO 146p, 17분)에서 관심 구간만 자르려면 범위 입력이 필요하다.
- 잘못 수집된 문서를 지우고 다시 돌리려는데, UI에는 보관(soft delete)만 있고 하드 삭제는 수동 스크립트로만 가능했다.

## 1. 페이지 범위 (`_parse_pages`)

`drheri_pipeline/sources/catalog_pdf.py`의 `_parse_pages(pages: str) -> list[int] | None` 확장:
- `""` → None (전체, 현행 유지)
- `"12"` → `[12]`
- `"12-26"` → `[12,13,…,26]`
- `"12-26, 30, 40-45"` → 혼합, 정렬·중복 제거
- 오류(명확한 `ValueError`): 숫자 아님, 하한 > 상한(`26-12`), 0 이하, 형식 불량(`12-`, `-5`, `1-2-3`)
- 모달 플레이스홀더: `예: 12-26, 30, 40-45`

## 2. 수집 초기화

문서는 유지하고 그 문서의 **수집 결과만** 지워 재수집 가능하게 한다.

**서비스** `drheri_pipeline/services/purge.py` — `reset_document(doc_id: int) -> dict`:
1. 이 문서 `image_origin`의 content_hash 수집
2. **전용 이미지**(다른 문서 image_origin에 없는 것)만 완전 삭제 대상, 공유 이미지는 보존
3. FiftyOne `drheri`에서 전용 해시 샘플 삭제 (실패해도 나머지 진행 — safe wrap)
4. 전용 이미지의 `rel_path` 파일 삭제 (review/training/rejected)
5. DB: `image_origin`(doc), 전용 `image`, `run`(doc) 삭제. **`document`·`brand`는 유지**
6. 반환: `{deleted_images, deleted_files, deleted_runs, kept_shared}`
- 원본 PDF(`document.url`이 가리키는 catalog 업로드본)와 raw 복사본은 **유지**(재수집이 다시 읽음)

**엔드포인트** `POST /api/sources/{id}/reset` → `reset_document` 실행 후 saved-views 재동기화, `{ok, data}` 반환. 문서 없으면 404.

**UI** (문서 상세): 액션 줄에 **"수집 초기화"** 버튼(빨강). 확인창에 지울 양 표시(`추출 N장`), 학습 승급분이 있으면 경고 한 줄. 실행 후 `load()`로 화면 갱신(퍼널 0).

## 3. 안전/에러

- 전용/공유 판별로 다른 문서의 이미지를 지우지 않는다.
- FiftyOne 미설치/오류 시에도 DB·파일 정리는 진행.
- 파괴적 동작이라 프론트 확인창 필수.

## 4. 테스트

- `_parse_pages`: 범위·혼합·정렬·중복제거·각 오류 케이스.
- `reset_document`: 전용 이미지·origin·run 삭제 / 문서·브랜드·공유이미지 유지 / 파일 삭제 / 퍼널 0. FiftyOne 삭제는 monkeypatch.
- API `POST /reset`: 200 + 반환 카운트, 404(없는 문서).
