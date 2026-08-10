"""systemd 서비스용 FiftyOne 런처 — manifest 에서 drheri 빌드 후 App 서빙.

env:
  FIFTYONE_PORT      (기본 5151)
  FIFTYONE_ADDRESS   (기본 0.0.0.0 — IP 직접 접속)
  FIFTYONE_CTL_PORT  (기본 5152 — 세션 뷰 제어, 127.0.0.1 전용)
  FIFTYONE_DATABASE_VALIDATION=false  (이 서버 mongo 4.4 사용 때문에 필수)

세션 뷰 제어(127.0.0.1:CTL_PORT) — 관리 UI '이 문서만 보기' 가 호출한다.
원격 App 은 단일 세션이라 URL ?view= 는 이전 필터와 충돌해 되돌아간다. session.view 를
서버에서 직접 세팅하면 필터 포함 뷰 전체를 원자적으로 교체해 항상 성공한다. 새 뷰는
호출 때 on-demand reload 로 반영(주기 reload 는 활성 뷰를 되돌릴 수 있어 쓰지 않는다).
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # fiftyone_review 임포트용

import fiftyone as fo  # noqa: E402
import fiftyone_review as R  # noqa: E402

port = int(os.getenv("FIFTYONE_PORT", "5151"))
addr = os.getenv("FIFTYONE_ADDRESS", "0.0.0.0")
ctl_port = int(os.getenv("FIFTYONE_CTL_PORT", "5152"))

ds = R.build_dataset()
R.build_views(ds)
print(f"drheri {ds.count()} samples → serving {addr}:{port} (ctl 127.0.0.1:{ctl_port})", flush=True)

session = fo.launch_app(ds, remote=True, port=port, address=addr)


class _Ctl(BaseHTTPRequestHandler):
    """GET /setview?doc=<id> → 공유 세션 뷰를 doc-<id> 로 원자적 교체(없으면 필터 해제)."""

    def do_GET(self):
        doc = (parse_qs(urlparse(self.path).query).get("doc") or [""])[0]
        out = b'{"ok":false}'
        try:
            ds.reload()                                   # 새로 생긴 뷰도 즉시 반영(on-demand)
            name = f"doc-{doc}"
            if doc and name in ds.list_saved_views():
                session.view = ds.load_saved_view(name)
                out = b'{"ok":true}'
            else:
                session.view = None                       # 전체(필터 해제)
                out = b'{"ok":true,"cleared":true}'
        except Exception as e:  # noqa: BLE001
            out = ('{"ok":false,"detail":"%s"}' % str(e).replace('"', "'")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


threading.Thread(
    target=lambda: HTTPServer(("127.0.0.1", ctl_port), _Ctl).serve_forever(),
    daemon=True).start()
session.wait(-1)
