"""systemd 서비스용 FiftyOne 런처 — manifest 에서 drheri 빌드 후 App 서빙.

env:
  FIFTYONE_PORT     (기본 5151)
  FIFTYONE_ADDRESS  (기본 0.0.0.0 — IP 직접 접속)
  FIFTYONE_DATABASE_VALIDATION=false  (이 서버 mongo 4.4 사용 때문에 필수)
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # fiftyone_review 임포트용

import fiftyone as fo  # noqa: E402
import fiftyone_review as R  # noqa: E402

port = int(os.getenv("FIFTYONE_PORT", "5151"))
addr = os.getenv("FIFTYONE_ADDRESS", "0.0.0.0")

ds = R.build_dataset()
R.build_views(ds)
print(f"drheri {ds.count()} samples → serving {addr}:{port}", flush=True)


def _auto_reload(interval=20):
    """장수 세션의 ds 는 launch 시점 스냅샷이라, 이후 다른 프로세스(수집/등록)가 만든
    saved view(수집마다 생기는 doc-<id>)를 모른다 → "이 문서만 보기"가 안 걸린다.
    주기적 reload 로 재기동 없이 최신 saved view 를 세션에 반영한다."""
    while True:
        time.sleep(interval)
        try:
            ds.reload()
        except Exception as e:  # noqa: BLE001
            print("auto-reload warn:", e, flush=True)


threading.Thread(target=_auto_reload, daemon=True).start()
session = fo.launch_app(ds, remote=True, port=port, address=addr)
session.wait(-1)
