---
name: reference-dgx-ssh
description: DGX Spark SSH 접속 정보 — 계정 metass, 전용 키 id_ed25519_dgx, 이 Windows PC에서 접속
metadata:
  type: reference
---

DGX Spark (AI TOP ATOM) SSH 접속 정보.

- **사용자 계정**: `metass`
- **전용 SSH 키**: `C:\Users\user\.ssh\id_ed25519_dgx` (+ `.pub`), ed25519, 패스프레이즈 없음, comment `dgx-spark-20260529`
- **공개키 지문**: `SHA256:vOnZuyY8RVcMrdwHPfMtCI/d6GcJgt1ObVoW24Jo05g`
- **접속 PC**: 이 Windows 11 PC (`c:\Heri2go` 작업 환경)
- **IP**: `192.168.0.27` (유선 enP7s7, LAN). WiFi(wlP9s9)는 미연결.
  - 이력: `192.168.0.132` → `192.168.0.27` 변경 (2026-06-15, DHCP 갱신)
  - 변경 시: `~/.ssh/config` HostName 갱신 + `ssh-keygen -R <old_ip>` + `ssh-keyscan -t ed25519 <new_ip> >> ~/.ssh/known_hosts`
- **호스트명**: `aitopatom-c681`
- **SSH config alias**: `dgx` 등록 완료 (`C:\Users\user\.ssh\config`). 키 인증 접속 확인됨 (2026-05-29).
- **호스트 키**: known_hosts에 192.168.0.132 (ED25519) 등록됨.

**How to apply:** 접속은 `ssh dgx` 한 줄. (수동: `ssh -i ~/.ssh/id_ed25519_dgx metass@192.168.0.132`). 공개키는 서버 `~/.ssh/authorized_keys`에 등록 완료. 다른 Heri2go 키(id_ed25519_devserver/drheri/ncloud 등)와 혼동 금지 — DGX 전용은 `id_ed25519_dgx`. IP는 현재 고정 IP인지 미확인 — 변경 시 config HostName 갱신 필요. [[project-dgx-spark]] 참조.

## 2026-06-10: 패스워드 인증 추가 활성화

PuTTY 등 키 등록이 번거로운 클라이언트 지원 위해 `PasswordAuthentication yes` 추가:

- 적용 파일: `/etc/ssh/sshd_config.d/99-keyonly.conf` (이 이름이지만 내용은 key+password 둘 다 허용)
- 백업 (원래 keyonly): `/etc/ssh/sshd_config.d/99-keyonly.conf.bak_20260610`
- metass 패스워드: 설정되어 있음 (P status). 사용자가 설정/변경은 `ssh dgx` 후 `passwd` 명령으로 직접
- 키 인증도 계속 작동 (`PubkeyAuthentication yes`)

### 다시 keyonly 로 복귀하려면
```bash
ssh dgx 'sudo cp /etc/ssh/sshd_config.d/99-keyonly.conf.bak_20260610 /etc/ssh/sshd_config.d/99-keyonly.conf && sudo systemctl reload ssh'
```

### 보안 메모
LAN 환경이라 위험 작지만 `fail2ban` 없음 — 사내망 신뢰 안 되는 디바이스 있으면 위험. 약한 패스워드 금지 (12자+ 권장).
