# DB 명세서 V1.1 검토 의견 (DevOps/BE)

> 작성: 2026-10-06 · 대상: DB 담당 `DB 명세서 V1.1 (임시)` — 서비스 스키마 `posture_service`, 테이블 26개(보류 2개 포함)
> 목적: 테스트 DB에서 DB 담당자가 새로 구축한 DB로 옮기기 전에, 지금 서버(api-server)가 새 DB에서 동작할 수 있는지 확인한다.
> 관련: `회의자료_DB스키마_매핑표.md`(V0.3 비교), `팀회의_안건_질문목록.md` Q1·Q13~Q18, `테스트DB_설정_이관가이드.md`

## 0. 결론

1. **지금 상태로 새 DB에 연결하면 api-server의 판정 기록이 전부 실패합니다.**
   api-server가 쓰는 데이터베이스는 `posture_app`이고, 테이블은 `sessions`·`collapse_events`입니다. V1.1에는 이 데이터베이스도, 이 테이블들도 없습니다.
   V1.1은 데이터베이스 이름이 `posture_service`이고 테이블 구조도 다릅니다.
2. **이관은 두 단계로 나누기를 제안합니다.**
   - 1단계(지금): 새 DB 서버에 **`posture_app`(현재 구조)과 `posture_service`(V1.1)를 함께** 만들고, 서버는 `posture_app`으로 연결합니다. 코드는 바꾸지 않고 DB 서버만 옮깁니다.
   - 2단계(팀 회의 Q1·Q13 결정 후): api-server를 V1.1에 맞게 바꾸고 `posture_app`을 없앱니다.
3. V1.1에는 지금 서버 구조(Kafka 비동기 처리)와 맞지 않는 테이블과, 성능상 확인이 필요한 부분이 있습니다(3장). 이 부분은 회의에서 DB 담당과 함께 정해야 합니다.

## 1. V1.1에서 달라진 점 (V0.3 대비)

| 구분 | 내용 |
|---|---|
| 추가 테이블 7개 (T-44~T-50, 건의안 0001·CR-03) | `input_result`(입력 처리 결과), `cep_outbox`(CEP 전달 대기), `confirmed_snapshot`(확정 요약), `cep_cleanup`(CEP 정리 재시도), `SPRING_SESSION`·`SPRING_SESSION_ATTRIBUTES`(로그인 세션), `client_record`(앱 기록 원문) |
| `user_account` 컬럼 추가 | `auth_epoch`(다른 기기 로그인 끊기), `age`, `occupation` |
| `excluded_interval` | 제외 사유에 `MISSING` 추가 (PAUSE / MISSING / ABSENCE / UNMEASURABLE) |
| `collapse_event` | `collapse_type_code` 추가 (유형 마스터 `collapse_type`은 보류) |
| 연구 스키마 24개 | 폐기 (학습 데이터는 HDFS에서 관리, BR-58) — 우리 결정(DN-20 연구DB 제거)과 일치 |

추가된 7개 테이블은 팀 저장소 `jin_app` 브랜치 백엔드(동기 REST + Esper CEP + Spring Session)가 쓰는 구조와 같습니다.
즉 V1.1은 `jin_app` 백엔드를 기준으로 설계가 확장된 상태입니다.

## 2. 현재 서버와 맞지 않는 부분

현재 api-server의 DB 사용(전부 `posture_app`):

| 현재 쓰는 곳 | 하는 일 | V1.1에서 대응하는 곳 | 차이 |
|---|---|---|---|
| `sessions` upsert (메시지마다) | 세션 시작·마지막 수신·샘플 수 | `monitor_session` | 사용자·장치·기준 자세·정책·모델 버전이 **외래키 필수** → 지금 수집 경로에는 이 값이 없음. 마지막 수신 시각·샘플 수 컬럼 없음 |
| `sessions` 만료 UPDATE (60초마다) | 5분 무응답 세션 종료 | `monitor_session.ended_at`, `end_reason=DISCONNECTED` | 마지막 수신 시각이 없어 DB만으로 판단 불가 → Redis로 옮기는 방안 제안 |
| `collapse_events` upsert | 붕괴 이벤트 시작·재알림·종료 | `collapse_event` + `correction_alert` | 세션 내 순번(`event_seq`)·확정 시각(`confirmed_at`) 필요, 재알림은 알림 1회 = 1행 |
| `accounts` | (거의 안 씀) | `user_account` | 사용자 ID가 문자열 → V1.1은 숫자 ID |
| `period_stats` | (비어 있음) | `daily_stat` | — |

세부 컬럼 비교는 `회의자료_DB스키마_매핑표.md` 2장과 같습니다(V0.3과 V1.1의 해당 테이블은 동일, `collapse_type_code`만 추가).

## 3. DB 담당과 확인할 사항

### 3.1 서버 구조 결정에 묶인 테이블 (회의 Q1)

- `input_result`·`cep_outbox`·`confirmed_snapshot`·`cep_cleanup`은 **"API가 HTTP로 CEP를 부르고, 실패하면 DB에 남겨 다시 보낸다"** 는 구조를 전제로 합니다.
- 우리 서버(아키텍처 v4)는 이 역할을 **Kafka**가 합니다. 메시지가 Kafka에 남아 있으므로, 컨슈머가 재시작해도 이어서 처리합니다.
- 회의에서 기준 백엔드(Q1)가 v4 쪽으로 정해지면 이 4개 테이블은 필요 없거나 용도가 바뀝니다. Q1이 정해질 때까지 확정을 미루기를 요청합니다.

### 3.2 입력마다 DB에 쓰는 구조의 성능

- `input_result`는 측정 입력 1건마다 1행을 쓰고, `cep_outbox`도 1행을 씁니다. 입력 1건에 DB 쓰기가 2번 일어납니다.
- 테스트 DB에서 측정한 실시간 판정의 한계는 **DB 쓰기 대기 때문에 초당 약 105~110건**이었습니다(T-11, 동시 12명 한계).
- 입력마다 쓰는 구조를 그대로 두면 같은 한계에 걸립니다. 다음 둘 중 하나를 요청합니다.
  - 새 DB 서버의 InnoDB 설정을 상향 (`테스트DB_설정_이관가이드.md` 4.2)
  - 입력 단위가 아니라 묶음 단위로 기록
- 참고로 `input_result`는 "세션당 최대 10,000건"으로 적혀 있습니다. 10Hz 전송이면 약 17분, v4 전송 주기(0.5초)면 약 83분 분량입니다. 장시간 측정 세션의 상한도 함께 정해야 합니다.

### 3.3 아직 비어 있는 시트

- 「쿼리 목록」과 「인덱스」 시트가 비어 있습니다(DB-05 작성 예정).
- 서버가 실제로 자주 쓰는 조회와 갱신은 다음과 같습니다. 인덱스 설계 때 근거 쿼리(Q-ID)로 넣어 주기를 요청합니다.
  - 진행 중인 세션 찾기: 세션 UUID로 조회 → UK-05로 충분
  - 세션 만료: 마지막 수신 시각 기준. Redis로 옮기면 DB 조회는 필요 없음
  - 이벤트 기록: (세션, 순번) → PK로 충분
  - 일별 통계 조회: (사용자, 날짜) → PK로 충분
  - 사용자별 최근 세션 목록: `monitor_session(user_account_id, started_at)` 인덱스 필요

### 3.4 시각 저장 기준 (UTC / KST)

- V1.1은 `joined_at`처럼 일부 컬럼에 "(UTC)"라고 명시하고, 나머지 일시 컬럼은 기준이 적혀 있지 않습니다. **모든 일시 컬럼을 UTC로 저장한다**고 명시해 주기를 요청합니다.
- 현재 서버의 JDBC 설정은 `serverTimezone=Asia/Seoul`이라, DATETIME에 **한국 시각**으로 저장되고 있을 가능성이 있습니다.
  - 반면 세션 만료 쿼리는 `UTC_TIMESTAMP()`와 비교합니다. 그러면 세션이 9시간 동안 만료되지 않는 문제가 생길 수 있습니다.
  - 이관 가이드 6장의 검증 쿼리로 먼저 확인하고, 맞다면 서버 설정을 UTC로 바꾸겠습니다.

### 3.5 물리 타입 매핑

- V1.1의 새 도메인(큰 정수·해시·ASCII 문자·JSON)이 CONVENTIONS 타입 매핑에 아직 없습니다.
- 실행 파일(`schema_V1_1.sql`)이 만들어지면 MySQL 8.0 기준 물리 타입을 같이 공유해 주기를 요청합니다.

## 4. 요청 정리 (DB 담당께)

| # | 요청 | 시점 |
|---|---|---|
| 1 | 새 DB 서버에 `posture_app`(현재 구조)도 함께 생성 — 1단계 이관용 | 이관 전 |
| 2 | 테스트 DB 설정 적용 (`테스트DB_설정_이관가이드.md`) | 이관 전 |
| 3 | 일시 컬럼 저장 기준을 UTC로 명시 | V1.1 확정 시 |
| 4 | `input_result`·`cep_outbox`·`confirmed_snapshot`·`cep_cleanup`은 회의 Q1 결정까지 확정 보류 | 회의 |
| 5 | 입력 단위 기록의 성능 기준·세션당 상한 재검토 | 회의 |
| 6 | 인덱스 설계에 `monitor_session(user_account_id, started_at)` 포함 | DB-05 |
| 7 | `schema_V1_1.sql` 실행 파일과 물리 타입 매핑 공유 | 확정 시 |
