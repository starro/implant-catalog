---
name: reference-drheri-implant-db
description: Dr.Heri implant master DB 스키마, 데이터 분포, 학습 자산 통계
metadata:
  type: reference
---

# Dr.Heri Implant Master DB 참조

## 위치

- **서버**: `drheri-op-web-api-2` (NCloud 1군 #2)
- **내부 IP**: `10.36.6.102` (VPN 필요)
- **공인 IP**: `118.67.132.58` (data.drheri.com)
- **OS/Stack**: CentOS 7.8, Apache + PHP 5.4.16 + MariaDB 5.5.68
- **DB 이름**: `drhericom`
- **연결 정보**: `_include/_db.php` (credential 평문 — 운영 시 로테이션 권장)
- **SSH**: `ssh -i ~/.ssh/id_ed25519_dgx root@10.36.6.102` (DGX 키 등록됨)
- **DocumentRoot**: `/home/drheri.data` (Apache vhost in `/etc/httpd/conf/virtuser.conf`)

## 핵심 테이블 (26개 중 학습/매칭에 중요한 것)

### `implant` (25,109 행) — 카탈로그 본체
```
i_id (PK), i_brand_id → brand, i_category_id → category, i_group (사이즈 변종 묶음용),
i_productcode (예: US4R4011S), i_level, i_pc_type, i_pc_feature, i_pc_diameter,
i_p_color, i_p_feature, i_p_neckdiameter, i_c_shape, i_c_micro (Y/N enum),
i_c_surface, i_m_shape, i_m_surface, i_surface_additional (enum),
i_a_shape, i_a_hole, i_a_groove, i_fbx (mediumblob — **모두 NULL** 확인됨),
i_length, i_diameter, i_apicaldiameter, i_surfaceheight, i_threadpitch
```
- 25,109 SKU → 2,524 unique (brand, category, group) — **collapse 평균 9.9배**
- spec 12차원 거의 100% 채워짐 (i_c_shape만 73.8%)

### `chart_implant` (126,587 행) — **학습 데이터 본체**
```
ci_id (PK), ci_chart_memo_id → chart_memo, ci_implant_id → implant (라벨),
ci_x, ci_y, ci_a, ci_w, ci_h, ci_l, ci_e (bbox),
ci_name (텍스트), ci_img_path (cropped fixture 파일 경로)
```
- 라벨 + 이미지 모두 있는 **usable pairs: 66,837 (52.8%)**
- 실제 디스크 cropped 파일: **60,093** (DB 라벨 - 실 파일 = ~6,744 dead reference)
- 평균 12.9KB / 파일

### `implant_xray` (576 행) — **검수된 골드셋 (OOS 평가용)**
```
ix_id (PK), ix_implant_id → implant, ix_xray_id → xray,
ix_x, ix_y, ix_w, ix_a (bbox — 4 필드만, 해석 미해결)
```
- 576 fixture가 181 panoramas에 분포
- ⚠️ bbox 컬럼 의미 미확정 — [[feedback-bbox-crop-unknown]]

### `xray` (181 행) — panoramas
```
x_id (PK), x_filename (DB값엔 한글 환자명 또는 메모 들어있음 — 실제 디스크 매핑 X),
x_tan, x_n00, x_panorama, x_comment
```
- **실제 디스크 파일은 `xray/org/<x_id>.jpg`** (181:1 매핑) — `x_filename` 컬럼 무시
- ⚠️ 한글 환자 정보 PII 가능 (실 파일은 숫자명, PII 0)

### `competitor_picture` (2,772 행) — 카탈로그 reference
```
cp_id (PK), cp_site enum('Whatimplantisthat','OSSEOsource','SpotImplant'),
cp_filename, cp_memo_details, cp_memo_feature
```
- 디스크: `/home/drheri.data/file/catalog/` 4.2GB / 474 파일 (17%만 실제 존재)

### `implant_represent` (2,694 행) — 카탈로그 대표 이미지
```
ir_id, ir_category_id, ir_implant_group, ir_implant_id,
ir_filename, ir_rep_flag, ir_type enum('modeling','xray'),
ir_leading_category_id
```
- modeling 2,588 / xray 106
- 디스크: `/home/drheri.data/file/implant_represent/` 50MB

### `brand` (208 행)
`b_id, b_name, b_country, b_description`

### `category` (2,085 행)
`c_id, c_brand_id, c_parent_id, c_name, c_description, c_torque, c_leading`

### 기타 — `chart_memo` (48,609), `chart` (22,853), `report_error` (5), `user_search` (7,958), `user_implant` (61), `admin`, `advertise`, `hospital`, `link`, `sales`, `scanbody`, `driver`, `asso_search`, `*_test` (legacy)

## 학습 데이터 가용성 통계 (2026-05-30)

| 항목 | 값 |
|------|---|
| chart_implant total | 126,587 |
| 라벨된 (ci_implant_id > 0) | 66,837 (52.8%) |
| 이미지 파일 존재 | 60,093 (10% dead reference) |
| **Unique 라벨된 implant 종** | **979** (전체 카탈로그의 3.9%) |
| 0-example implant | 24,130 (long-tail) |

### Long-tail 분포 (라벨된 인스턴스 수별 implant 종 수)
```
1 (singleton):    111 종 (학습 사실상 불가)
2-4 examples:     174 종 (sparse)
5-19:             317 종 (저정밀 fine-tune)
20-99:            233 종 (정상)
100-499:          113 종 (양호)
>=500:             31 종 (탁월, 28,411 instances 43%)
```

### Brand 분포 (실 사용량 기준)
```
OSSTEM IMPLANT   16,428 (26%)
Dentsply Sirona  14,013
Straumann        12,263
NEOBIOTECH        5,990
DIO IMPLANT       3,986
Nobel Biocare     2,916
DENTIUM           2,814
Point Implant     2,687
─────────────── 합 ≈ 61,097 (95%)
Zimmer Dental       976, DENTIS 915, BIOMET 3i 886, Thommen 718,
Hiossen 438, IBS 374, MEGAGEN 357, ...
```

## Top 모델 (instances 500+, 31종)
```
24952 (Dentsply Sirona Astra Tech OsseoSpeed TX)  2,960
021.4410 (Straumann Bone Level NC SLA)             1,616
US4R4010S (OSSTEM USIV SA)                         1,534
021.6410 (Straumann Bone Level NC SLA)             1,505
24962 (Dentsply Sirona)                            1,396
EB4510A (NEOBIOTECH Regular 4.0/4.5)               1,391
24951                                              1,291
24942                                              1,025
US4R4510S                                            961
24941                                                957
... (총 31종이 28,411 instances = 라벨된 데이터의 43%)
```

## 카탈로그 spec ontology (12차원) — Android Bundle 키 ↔ DB 컬럼

| Bundle key (Android) | DB 컬럼 | 옵션 값 (int → 문자열) |
|---------------------|---------|----------------------|
| connection_type | i_pc_type | 0=Onebody, 1=External, 2=Internal |
| connection_feature | i_pc_feature | 0=none, 1=Hex, 2=Octa, 3=Double hex, 4=Tri channel, 7=Six channel, 8/9/10=Three/Four/Six cam, 11=Round, 12=Misc, 13/14=Four/Eight channel, 15=Quad |
| connection_color | i_p_color | 0x_RGB hex (Gray, Red, Blue, Green, Yellow, Purple, Pink, White, Brown) |
| level | i_level | 1=Bone, 2=Tissue, 3=Multi |
| coronal_design | i_c_surface | 0=No threads, 1=Square, 2=Rounded, 3=V Shaped, 4=Buttress, 5=Reverse buttress, 6=Fin |
| microthread | i_c_micro | Y/N |
| middle_design | i_m_surface | (coronal_design과 동일 옵션) |
| middle_shape | i_m_shape | 1=Tapered, 2=Straight, 3=semi-Tapered |
| apical_shape | i_a_shape | 1=Cone, 2=Dome, 3=Flat, 4=Flared |
| apical_hole | i_a_hole | 0=No, 1=Round, 2=Oblong |
| apical_groove | i_a_groove | 0=No, 1=Yes |
| (사용 안 됨) | i_pc_feature, i_p_feature, i_c_shape | — |

→ 신규 AI의 attribute 출력은 **이 enum과 일치**해야 백엔드와 호환 (재정의 금지).

## 백엔드 API 엔드포인트 (`data.drheri.com/app/api_v1/`)

- `search_image/` — **현재 스텁** (이미지 무시, 하드코딩 SQL). 우리가 대체할 대상.
- `search_feature/` — 사용자 spec 선택 → AND 필터 SQL (정상 동작, 그룹 collapse)
- `count_implants/` — spec 조합 → COUNT(*) 미리보기
- `implant/` — `iid+sid` → 상세 + 유사
- `producer/` — 제조사 리스트
- `save_implant/`, `save_implant_delete/`, `saved_implants/`, `tag_implant/`, `report_error/` — 보조

응답 형식 (drop-in 호환 필요):
```json
{"data": [{"ii": 1234, "bi": 7, "pn": "OSSTEM IMPLANT", "bn": "TSIII CA", "im": "TS3R4010C", "rf": "img.png", "rx": "xray.png", "ic": 8}], "code": 0, "msg": "ok"}
```

## 이미지 디스크 경로

- chart_implant (학습) → `/home/drheri.data/clip_implant/<brand>/<series>/<model>/<id>.jpg` (60,093 / 879MB)
- xray panoramas → `/home/drheri.data/xray/org/<x_id>.jpg` (181 / ~3GB 일부)
  - 그 외 서브폴더: `xray/chart_xray/` (53,349), `xray/chart_xray2/` (9), `xray/competitior_picture/` (1,105)
- implant_represent → `/home/drheri.data/file/implant_represent/` (2,578 / 50MB)
- competitor_picture catalog → `/home/drheri.data/file/catalog/` (4.2GB / 474 파일)

## 이전 AI 시도 (참고용, 모두 미완성/구식)

- `AI_Search/index.php` (2022-01): `http://dev.kpst.co.kr:50080/implant-cls` 외주 호출 (현재 **DNS 소멸**)
- `ai/model_by_img/test_index.php` (2023-02): test_parents 테이블 매핑 SQL 테스트
- `clip_implant/` (2022-01): 폴더 이름은 "CLIP"이지만 실제론 단순 cropped fixture 저장소 (CLIP 모델과 무관)
- `implant_test/diameter_all/` (2022-01): 직경 측정 실험

[[project-drheri-app-architecture]] [[project-drheri-implant-ai]] 참조.
