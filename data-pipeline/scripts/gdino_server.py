"""GPU 컨테이너용 Grounding DINO HTTP 서비스 (웜 유지). 컨테이너 안에서:
    python scripts/gdino_server.py            # :8100
transformers 4.57 규약: post_process_grounded_object_detection(threshold=, text_threshold=)."""
import base64
from io import BytesIO

import torch
import uvicorn
from fastapi import FastAPI
from PIL import Image
from transformers import AutoProcessor, GroundingDinoForObjectDetection

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_proc = AutoProcessor.from_pretrained("IDEA-Research/grounding-dino-base")
_model = GroundingDinoForObjectDetection.from_pretrained(
    "IDEA-Research/grounding-dino-base").to(DEVICE).eval()
app = FastAPI()


@app.post("/detect")
def detect(body: dict):
    img = Image.open(BytesIO(base64.b64decode(body["image_b64"]))).convert("RGB")
    text = body.get("prompt", "an implant fixture.")  # 끝 마침표 필수(Grounding DINO 쿼리 관례)
    thr = float(body.get("threshold", 0.3))
    inp = _proc(images=img, text=text, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        out = _model(**inp)
    res = _proc.post_process_grounded_object_detection(
        out, inp.input_ids, threshold=thr, text_threshold=thr,
        target_sizes=[img.size[::-1]])[0]
    boxes = [{"score": round(float(s), 3),
              "xyxy": [int(v) for v in box.tolist()]}
             for box, s in zip(res["boxes"], res["scores"])]
    return {"boxes": boxes}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
