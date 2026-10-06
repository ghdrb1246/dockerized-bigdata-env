# 회의 자료 — DB 스키마 매핑표 (`posture_app` ↔ V0.3 ↔ v4)

> 작성: 2026-10-05 · 관련: D-03(통계 집계), D-14b(팀 결정 안건 6), `회의안건_D-03_통계테이블_매핑.md`, `팀저장소_분석_2026-10-05.md`
> 비교 대상
> - **현재 운영** `posture_app` — 우리 저장소 `mysql/posture_app_schema.sql`, 테스트 DB 192.168.0.42에 적용됨. api-server가 실제로 쓰는 스키마
> - **V0.3** `posture_service` — 팀 저장소 `develop` 브랜치 `database/schema/schema_V0_3.sql` (DB 담당, 10/02, 테이블 17개 + 시드 4종)
> - **v4** — `Posture_Architecture_v4.md` 5.12절 (테이블 이름·주요 컬럼만 정의)

## 0. 요약

1. **V0.3이 가장 완성도가 높다.** 외래키·CHECK 제약·시드까지 갖췄고, `daily_stat`(통계)·`feature_archive`(HDFS 파일 위치)처럼 우리 플랫폼 구성과 맞는 테이블도 있다. **V0.3을 기준으로 채택하고 우리 코드가 맞추는 방향을 제안**한다.
2. 그대로 쓰려면 막히는 점이 세 가지 있다.
   - **세션을 만들기 전에 필요한 값이 많다.** `monitor_session`이 사용자·장치·기준 자세·판정 정책·모델 버전을 모두 외래키로 요구한다. 지금 우리 수집 경로는 `userId` 문자열과 `sessionId`만 받고 "세션 시작" 단계가 없다.
   - **세션 만료에 쓰는 값이 없다.** `monitor_session`에 `last_seen_at`이 없어서, 지금의 "5분 무응답 세션 만료"(DN-19)를 DB만으로는 할 수 없다.
   - **판정 엔진이 지금 기록하지 않는 값을 요구한다.** 이벤트 순번(`event_seq`), 확정 시각(`confirmed_at`), 알림 시도별 행(`correction_alert`), 바른 자세 시간(`good_sec`).
3. **좋은 점도 있다.** V0.3은 샘플마다 DB를 쓰지 않고 **세션 시작·종료·이벤트·알림 때만 쓰는 구조**다. 지금 우리 병목이었던 "샘플마다 `sessions` upsert"(D-15/D-17)가 구조적으로 사라진다. 마지막 수신 시각은 v4 설계대로 Redis `session:{sessionId}`에 두면 된다.
4. 판정 파라미터가 네 곳에서 서로 다르다(5장). 특히 V0.3 시드 기본값은 **임계값 0.5 / 재알림 30초**로, 다른 어느 쪽과도 같지 않다.

## 1. 테이블 대응

| 역할 | 현재 `posture_app` | V0.3 `posture_service` | v4 |
|---|---|---|---|
| 사용자 | `accounts` | `user_account` | `users` |
| 측정 장치 | — | `capture_device` | — |
| 기준 자세 | `baseline_postures` (JSON 1컬럼) | `baseline_posture` + `baseline_feature` (특징별 평균·표준편차) | `baselines` |
| 특징 정의 | — | `feature_def` (HEAD_GAP / LATERAL_OFFSET / SHOULDER_TILT) | — |
| 판정 정책 | (설정 파일 `cep.*`) | `threshold_policy` (값 조합, 변경 금지) | — |
| 모델 버전 | — | `model_version` | `model_versions` |
| 측정 세션 | `sessions` | `monitor_session` | `sessions` |
| 제외 구간 | — | `excluded_interval` (PAUSE / ABSENCE / UNMEASURABLE) | — |
| 붕괴 이벤트 | `collapse_events` | `collapse_event` | `episodes` |
| 알림 | (`collapse_events.alert_count`) | `correction_alert` (시도 1건 = 1행) | — |
| 일별 통계 | `period_stats` (비어 있음) | `daily_stat` | `mart_daily_posture` |
| HDFS 적재 기록 | — | `feature_archive` | — |
| 삭제 요청·배포·오류 | — | `deletion_request`, `deployment`, `error_log` | — |

DB 이름도 다르다: `posture_app` vs `posture_service`. MySQL 버전 요건(8.0.16+, CHECK 제약)은 테스트 DB(8.0.25)가 충족한다.

## 2. 컬럼 매핑

### 2.1 세션: `sessions` → `monitor_session`

| `sessions` (현재) | `monitor_session` (V0.3) | 비고 |
|---|---|---|
| `session_id` VARCHAR(64) PK | `client_session_uuid` CHAR(36) UNIQUE + `monitor_session_id` BIGINT PK | 지금 sessionId가 UUID라 길이는 맞음. 이벤트 테이블은 BIGINT PK로 참조 |
| `user_id` VARCHAR(64) | `user_account_id` BIGINT FK | **문자열 → 계정 ID 변환 필요** (인증 D-07 전까지 방법 결정) |
| `started_at` | `started_at` | 같음 |
| `ended_at` | `ended_at` + `end_reason` (USER_STOP / DISCONNECTED / ERROR) | 우리 만료 처리 = `DISCONNECTED` |
| `last_seen_at` | **없음** | 만료 판단용 → Redis `session:{sessionId}.lastInferenceAt`(v4)로 이동 제안 |
| `sample_count` | **없음** | 필요하면 Redis 또는 컬럼 추가 요청 |
| `status` (ACTIVE / ENDED) | `ended_at IS NULL` 여부 | 파생 |
| — | `capture_device_id`, `baseline_posture_id`, `threshold_policy_id`, `model_version_code` (모두 FK, NOT NULL) | **세션 시작 시점에 확정돼 있어야 함** |
| — | `alert_enabled`, `frame_width`, `frame_height` | FE가 세션 시작 때 보내야 함 |
| — | `good_sec` (종료 시 기록) | 판정 엔진이 바른 자세 시간을 누적해야 함 |

### 2.2 이벤트: `collapse_events` → `collapse_event` + `correction_alert`

| `collapse_events` (현재) | V0.3 | 비고 |
|---|---|---|
| `id` + UNIQUE(`session_id`, `started_at`) | PK(`monitor_session_id`, `event_seq`) | 엔진이 세션별 순번을 관리해야 함 |
| `started_at` | `started_at` "임계를 넘은 시각" | 우리 `candidateSince`와 정의가 같음 ✅ |
| — | `confirmed_at` "지속 조건 충족 시각" | 엔진에 값은 있으나 재알림 때 덮어씀 → 별도 필드로 보관 필요 |
| `ended_at` | `ended_at` + `end_reason` (RECOVERED / SESSION_END / EXCLUDED) | 회복 = RECOVERED, 세션 만료 강제 종료 = SESSION_END |
| `recovered` | `recovered_at` (RECOVERED일 때만) | 파생 |
| `duration_seconds` | 없음 | `ended_at − started_at`으로 계산 |
| `alert_count`, `last_alert_at` | `correction_alert` 행 수·최신 `attempted_at` | **알림 1회 = 1행 INSERT**로 바뀜. `delivered`, `suppress_reason`(시간당 상한 등)도 기록 |
| `ongoing` | `ended_at IS NULL` | 파생 |
| `user_id` | 없음 (세션 경유) | 정규화 |

### 2.3 통계: `period_stats` → `daily_stat`

| `period_stats` (현재) | `daily_stat` (V0.3) | 비고 |
|---|---|---|
| `id` | PK(`user_account_id`, `stat_date`) | 같은 날 재집계는 upsert로 멱등 |
| `period_start` / `period_end` | `stat_date` (`STAT_TIMEZONE` 기준, 세션 시작 날짜 귀속) | 회의 안건 2의 BE 제안과 같음 |
| `valid_seconds` | `valid_sec` DECIMAL(9,1) | 단위: 초 (회의 안건 3 → V0.3은 초) |
| `normal_ratio` | `good_sec / valid_sec` | 조회 시 계산 |
| `collapse_count` | `event_count` (+ `alerted_event_count`) | |
| `collapse_per_hour` | 없음 | 조회 시 계산 |
| `avg_` / `median_duration_seconds` | 없음 | `collapse_event`에서 계산하거나 컬럼 추가 요청 |
| `model_version` | 없음 | 세션 → `model_version_code`로 추적 가능 |
| `computed_at` | `computed_at` | 같음 |
| — | `session_count` | |

### 2.4 그 외

- `accounts(user_id, display_name)` → `user_account(BIGINT, login_email, password_hash, display_name, account_status, threshold_policy_id …)` — 인증(D-07)과 함께 전환.
- `baseline_postures(feature_json)` → `baseline_posture`(보정 UUID, 화면 위치, 표본 수) + `baseline_feature`(특징별 평균·표준편차) — 캘리브레이션 API(FR-BE-11)와 함께 전환.

## 3. 현재 파이프라인을 V0.3에 맞출 때 필요한 BE 변경

| # | 변경 | 규모 | 비고 |
|---|---|---|---|
| 1 | **세션 시작 단계 추가**: 세션 생성 API(또는 첫 메시지)에서 사용자·장치·기준 자세·정책·모델 버전을 확정하고 `monitor_session` INSERT | 중 | FE가 세션 시작 때 장치·해상도·기준 자세 ID를 보내야 함 → FE 담당 협의 |
| 2 | 샘플마다 하던 `sessions` upsert 제거 → 마지막 수신 시각은 Redis `session:{sessionId}` | 소 | D-15/D-17의 DB 쓰기 병목이 근본적으로 줄어듦 |
| 3 | 엔진 상태에 `event_seq`, `confirmed_at`, 바른 자세 누적 시간 추가 (Redis 상태 D-04에도 반영) | 소~중 | |
| 4 | 재알림을 `correction_alert` INSERT로 기록, 시간당 상한(`notify_max_per_hour`) 억제 로직 | 중 | 상한 억제는 새 기능 |
| 5 | 세션 종료(`ended_at`, `end_reason`, `good_sec`) 기록 — 명시 종료 API + 만료 시 `DISCONNECTED` | 소 | |
| 6 | `excluded_interval`(일시정지·자리 비움·측정 불가) — 지금 엔진에 개념 없음 | 중 | 추론 결과에 측정 불가 상태가 와야 함 → 모델/FE 협의 |
| 7 | `daily_stat` 집계 (D-03): 처음엔 SQL 배치, 이후 Spark J3 | 중 | |
| 8 | `feature_archive` — HDFS 적재(posture-sink / Spark J1) 결과를 기록 | 소 | 우리 HDFS 경로와 바로 연결 가능 |

## 4. `userId` 문자열 문제 (인증 전 단계)

지금 클라이언트는 `userId`를 자유 문자열(`P01`, `P001` 등)로 보내고, V0.3은 `user_account_id` BIGINT 외래키를 요구한다.

- (A) 인증(D-07) 전까지 테스트용 계정을 시드로 만들고, `display_name` 또는 별도 매핑으로 문자열과 연결한다
- (B) 인증을 먼저 하고 세션 생성을 로그인 사용자 기준으로 한다
- **BE 제안: A로 파이프라인을 먼저 옮기고, D-07에서 B로 바꾼다.**

## 5. 판정 파라미터 불일치

| 출처 | 임계값 | 지속 (T1) | 회복 (T2) | 재알림 (T3) | 시간당 알림 상한 |
|---|---|---|---|---|---|
| 우리 api-server (DN-07 검증값) | (추론 결과 사용) | 3초 | 3초 | 60초 | 없음 |
| 팀 FE `main` / `jin_app` | 0.7 | 3초 | 2초 | 60초 | 없음 |
| **V0.3 시드 `DEFAULT_TEMP`** | **0.5** | 3초 | 2초 | **30초** | **12회** |
| v4 초안 | 0.5 | 10초 | 5초 | 60초 | — |

V0.3은 정책을 `threshold_policy` 테이블에 두고 세션마다 참조한다. 값이 정해지면 우리 설정(`cep.*`)도 이 테이블에서 읽도록 바꾸는 것을 제안한다.

## 6. 회의에서 정할 것

1. V0.3을 서비스 DB 기준 스키마로 채택하는가 (DB 이름 `posture_service`)
2. `monitor_session`에 `last_seen_at`을 추가할지, 아니면 Redis로 처리할지 (BE 제안: Redis)
3. 세션 시작 시 FE가 보낼 값(장치 키, 해상도, 기준 자세 ID, 알림 사용 여부)
4. 인증 전 `userId` 처리 방식 (4장)
5. 기본 판정 정책 값 하나로 확정 (5장)
6. `daily_stat`에 평균·중앙 지속시간 컬럼을 추가할지 (계획서 "주기 분석" 지표)
7. 일시정지·자리 비움·측정 불가(`excluded_interval`)를 누가 판단하는가 — FE / 추론 / 판정 엔진
8. `jin_app` 브랜치의 Flyway V1 스키마는 폐기하는가 (팀 저장소 분석 5장 안건 1과 연동)
