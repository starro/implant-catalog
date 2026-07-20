"""systemd 서비스용 FiftyOne 런처 — manifest 에서 drheri 빌드 후 App 서빙.

env:
  FIFTYONE_PORT     (기본 5151)
  FIFTYONE_ADDRESS  (기본 0.0.0.0 — IP 직접 접속)
  FIFTYONE_DATABASE_VALIDATION=false  (이 서버 mongo 4.4 사용 때문에 필수)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # fiftyone_review 임포트용

import fiftyone as fo  # noqa: E402
import fiftyone_review as R  # noqa: E402

port = int(os.getenv("FIFTYONE_PORT", "5151"))
addr = os.getenv("FIFTYONE_ADDRESS", "0.0.0.0")

ds = R.build_dataset()
R.build_views(ds)
print(f"drheri {ds.count()} samples → serving {addr}:{port}", flush=True)

session = fo.launch_app(ds, remote=True, port=port, address=addr)
session.wait(-1)
