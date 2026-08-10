"""GPU 컨테이너용 Grounding DINO HTTP 서비스 (웜 유지). 컨테이너 안에서:
    python scripts/gdino_server.py            # :8100
transformers 4.57 규약: post_process_grounded_object_detection(threshold=, text_threshold=).

자가복구: cuDNN 컨텍스트가 오염되면(RuntimeError "unable to find an engine ...") 이후 모든
추론이 전염된다. detect/health 는 실패 시 empty_cache 재시도 → 모델 재로드 재시도로 스스로 복구한다.
/health 는 tiny 실추론으로 conv 경로까지 살아있는지 확인 → engine.status 가 고장을 감지한다.
"""
import base64
import threading
from io import BytesIO

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from PIL import Image
from transformers import AutoProcessor, GroundingDinoForObjectDetection

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_ID = "IDEA-Research/grounding-dino-base"
_proc = AutoProcessor.from_pretrained(MODEL_ID)
_model = GroundingDinoForObjectDetection.from_pretrained(MODEL_ID).to(DEVICE).eval()
_reload_lock = threading.Lock()
_gen = 0                      # 모델 세대 — 중복 재로드 방지
app = FastAPI()


def _run(img, text, thr):
    inp = _proc(images=img, text=text, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        out = _model(**inp)                       # 전역 _model — 재로드 후엔 새 모델을 집는다
    res = _proc.post_process_grounded_object_detection(
        out, inp.input_ids, threshold=thr, text_threshold=thr,
        target_sizes=[img.size[::-1]])[0]
    return [{"score": round(float(s), 3), "xyxy": [int(v) for v in box.tolist()]}
            for box, s in zip(res["boxes"], res["scores"])]


def _reload_model(seen_gen: int) -> None:
    """CUDA/cuDNN 오염 시 모델을 새로 올린다(직렬화). 다른 스레드가 이미 올렸으면 스킵."""
    global _model, _gen
    with _reload_lock:
        if seen_gen != _gen:                      # 그새 누가 재로드함 — 중복 로드 회피
            return
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
        _model = GroundingDinoForObjectDetection.from_pretrained(MODEL_ID).to(DEVICE).eval()
        _gen += 1


def _detect_with_recovery(img, text, thr):
    """추론 실패(cuDNN 엔진 못 찾음 등) 시: empty_cache 재시도 → 모델 재로드 재시도."""
    try:
        return _run(img, text, thr)
    except RuntimeError:
        g = _gen
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
        try:
            return _run(img, text, thr)           # 1차: 캐시 비우고 재시도
        except RuntimeError:
            _reload_model(g)                      # 2차: 모델 새로 로드 후 재시도
            return _run(img, text, thr)


@app.post("/detect")
def detect(body: dict):
    img = Image.open(BytesIO(base64.b64decode(body["image_b64"]))).convert("RGB")
    text = body.get("prompt", "an implant fixture.")  # 끝 마침표 필수(Grounding DINO 쿼리 관례)
    thr = float(body.get("threshold", 0.3))
    try:
        return {"boxes": _detect_with_recovery(img, text, thr)}
    except Exception as e:  # noqa: BLE001 — 복구까지 실패하면 500 (runner 가 페이지 격리)
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


@app.get("/health")
def health():
    """tiny 실추론으로 conv 경로까지 확인. 죽었으면 자가복구 시도. 복구 실패만 503."""
    try:
        _detect_with_recovery(Image.new("RGB", (96, 96), (180, 180, 180)),
                              "an implant fixture.", 0.3)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "detail": f"{type(e).__name__}: {e}"}, status_code=503)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
