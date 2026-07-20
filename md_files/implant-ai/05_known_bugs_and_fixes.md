---
name: feedback-implant-ai-ct-filter-bug
description: implant-ai-web 의 visibleResults filter 가 양수 cosine (좋은 매치) 을 가리던 버그 (2026-06-08 수정)
metadata:
  type: feedback
---

# implant-ai-web `ct` filter 버그 (2026-06-08 수정)

## 버그

[c:/projects/implant-ai-web/app/pages/index.vue:154](c:/projects/implant-ai-web/app/pages/index.vue#L154) 의 `visibleResults` 가 거꾸로 동작.

```js
// BUG
const visibleResults = computed(() => (result.value?.data || []).filter(d => ((d.ct ?? 0) + 1) <= 1))
```

조건 `(ct + 1) <= 1` ⇒ `ct <= 0`. 즉 **음수 cosine 만 통과**. 양수 cos (좋은 매치) 가 화면에서 모두 가려짐.

DGX 의 `search_image_v2` 출력 `ct` = raw cosine similarity ([-1, 1]). 정상 매치는 양수 → 화면에서 가려졌어야 함.

## 왜 production 에서 안 터졌나

당시 ArcFace head 가 production query 와 반대 방향에 학습돼 있어서 raw cos 가 **-0.39 ~ -0.42** (음수) 로 나옴. filter `ct <= 0` 가 통과시킴 → 결과 화면에 표시. 우연히 버그가 가려진 상태.

CLAHE preprocessing + v2_aug 학습으로 classifier raw cos 가 **+0.20** 양수가 되자 filter 가 모든 결과를 가리기 시작 → "결과가 하나도 안 나와" 증상.

## 수정

```js
// FIX (2026-06-08): filter 제거, DGX top-K 그대로 신뢰
const visibleResults = computed(() => result.value?.data || [])
```

## 화면 score 변환 (참고)

[index.vue:42](c:/projects/implant-ai-web/app/pages/index.vue#L42), [:67](c:/projects/implant-ai-web/app/pages/index.vue#L67), [:130](c:/projects/implant-ai-web/app/pages/index.vue#L130) 에서:

```js
((item.ct ?? 0) + 1).toFixed(4)  // 화면에 표시되는 score = raw cos + 1
```

→ 화면 score 0.9892 = raw cos **-0.0108** (음수 → 거의 random 매치)
→ 화면 score 1.8849 = raw cos **+0.8849** (강한 매치)

**숫자 그대로 보지 말 것** — 0~2 범위. 1.0 이 random match 기준.

추후 UX 개선 권장: `((ct + 1) / 2) * 100` % 식 [0, 100] 변환이 직관적.

## How to apply

- implant-ai-web 의 filter / threshold 코드 변경 시 raw cos 부호와 화면 변환 항상 분리해서 검토
- ArcFace head 학습 결과에 따라 production cos 가 음수/양수 양쪽 다 나올 수 있다는 점 인지
- DGX serve 가 반환하는 `ct` 는 변환 없는 raw value, frontend 단에서 표시용 변환만

**Why:** 모델 개선으로 cos 부호가 바뀌자 숨어있던 frontend 버그가 드러남. 모델 출력 단에선 항상 raw cos 를, 표시 단에선 직관적 score 변환만, 두 layer 분리가 안전.

**관련:** [[feedback-bbox-crop-unknown]] (DGX serve 구조 분석), [[project-drheri-implant-ai]]
