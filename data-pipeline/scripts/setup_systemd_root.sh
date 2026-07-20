#!/usr/bin/env bash
# root 로 실행 — 방화벽 포트 개방 + Dagster/FiftyOne systemd 서비스 등록.
#   (개발서버 58.229.105.3 / root 는 su - 로 전환. 서비스는 jay8126 권한으로 실행)
# 사용: su - 후  bash /tmp/setup_systemd_root.sh
set -e

U=jay8126
H=/home/$U/drheri-pipeline
PY=$H/.venv/bin/python

echo "=== 1) 방화벽 포트 개방 (3333 Dagster / 5151 FiftyOne) ==="
firewall-cmd --permanent --add-port=3333/tcp >/dev/null
firewall-cmd --permanent --add-port=5151/tcp >/dev/null
firewall-cmd --reload >/dev/null
echo "열린 포트: $(firewall-cmd --list-ports)"

echo "=== 2) 기존 nohup 프로세스 정리 ==="
pkill -u $U -f "[d]agster" 2>/dev/null || true
pkill -u $U -f "[l]aunch_app" 2>/dev/null || true
sleep 2

echo "=== 3) systemd 유닛 생성 ==="
cat > /etc/systemd/system/drheri-dagster.service <<EOF
[Unit]
Description=Dr.HERi Dagster (data pipeline)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$U
WorkingDirectory=$H
Environment=PATH=/home/$U/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$H
Environment=DATA_ROOT=$H/data
Environment=DAGSTER_HOME=$H/.dagster_home
Environment=HF_HOME=$H/hf_cache
Environment=FIFTYONE_DATABASE_VALIDATION=false
Environment=HOOK_TOKEN=drheri-dev
Environment=UI_BASE_URL=http://127.0.0.1:3000
ExecStart=$PY -m dagster dev -m drheri_pipeline.definitions --host 0.0.0.0 --port 3333
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/drheri-fiftyone.service <<EOF
[Unit]
Description=Dr.HERi FiftyOne (labeling UI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$U
WorkingDirectory=$H
Environment=PATH=/home/$U/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$H
Environment=DATA_ROOT=$H/data
Environment=HF_HOME=$H/hf_cache
Environment=FIFTYONE_DATABASE_VALIDATION=false
Environment=FIFTYONE_PORT=5151
Environment=FIFTYONE_ADDRESS=0.0.0.0
ExecStart=$PY $H/scripts/serve_fiftyone_service.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "=== 4) 등록 + 기동 ==="
systemctl daemon-reload
systemctl enable drheri-dagster drheri-fiftyone >/dev/null 2>&1
systemctl restart drheri-dagster drheri-fiftyone
sleep 6
echo "=== 5) 상태 ==="
systemctl is-active drheri-dagster drheri-fiftyone || true
ss -tln | grep -E ":3333|:5151" || echo "  (아직 리스닝 전 — 기동 중일 수 있음)"
