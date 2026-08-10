#!/usr/bin/env bash
# root 로 실행 — 관리 UI(:3000) systemd 등록 + FiftyOne 재기동 sudo 권한 부여.
# 사용: su - -c "bash /home/jay8126/Dr.HERi/data-pipeline/scripts/setup_ui_root.sh"
set -e

U=jay8126
# H 는 이 스크립트의 실제 위치에서 유도한다(스크립트가 scripts/ 밑에 있다고 가정).
# 저장소를 다른 경로에 둔 경우 H=/other/path bash setup_ui_root.sh 처럼 환경변수로 덮어쓸 수 있다.
H="${H:-$(cd "$(dirname "$0")/.." && pwd)}"
PY=$H/.venv/bin/python

echo "=== 1) UI 가 FiftyOne 정지/기동/재기동할 수 있게 sudo 권한 허용 ==="
echo "$U ALL=(root) NOPASSWD: /usr/bin/systemctl stop drheri-fiftyone, /usr/bin/systemctl start drheri-fiftyone, /usr/bin/systemctl restart drheri-fiftyone" > /etc/sudoers.d/drheri-ui
chmod 440 /etc/sudoers.d/drheri-ui
visudo -c >/dev/null && echo "  sudoers OK"

echo "=== 2) 방화벽 3000 확인 ==="
firewall-cmd --permanent --add-port=3000/tcp >/dev/null 2>&1 || true
firewall-cmd --reload >/dev/null 2>&1 || true

echo "=== 3) UI systemd 유닛 ==="
cat > /etc/systemd/system/drheri-ui.service <<EOF
[Unit]
Description=Dr.HERi 데이터 파이프라인 관리 UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$U
WorkingDirectory=$H
Environment=PATH=/home/$U/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$H
Environment=DATA_ROOT=$H/data
Environment=FIFTYONE_DATABASE_VALIDATION=false
Environment=HOOK_TOKEN=drheri-dev
Environment=UI_BASE_URL=http://127.0.0.1:3000
Environment=FIFTYONE_URL=http://58.229.105.3:5151
Environment=FIFTYONE_SERVICE=drheri-fiftyone
ExecStart=$PY -m uvicorn drheri_pipeline.ui.app:app --host 0.0.0.0 --port 3000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable drheri-ui >/dev/null 2>&1
systemctl restart drheri-ui
sleep 5
echo "=== 4) 상태 ==="
systemctl is-active drheri-ui || true
ss -tln | grep ":3000" || echo "  (아직 리스닝 전)"
