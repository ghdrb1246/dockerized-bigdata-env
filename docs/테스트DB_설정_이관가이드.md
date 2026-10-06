# 테스트 DB 설정 이관 가이드 (DB 담당용)

> 작성: 2026-10-06 · 작성: DevOps/BE
> 대상: DB 담당자가 새로 구축한 MySQL 서버
> 목적: 지금 테스트 DB(Windows, MySQL 8.0.25)에 적용해 둔 설정을 새 DB 서버에 똑같이 적용해, api-server를 새 DB로 옮겨도 그대로 동작하게 한다.
> 관련: `DB_V1.1_검토의견.md`(1단계 이관: `posture_app`과 `posture_service`를 함께 둠), 저장소 `mysql/README_MySQL_구축_가이드.md`, `mysql/posture_app_schema.sql`

## 0. 요약 체크리스트

| # | 작업 | 필수 | 재시작 |
|---|---|---|---|
| 1 | `bind-address = 0.0.0.0` | 필수 | MySQL 재시작 |
| 2 | 방화벽 TCP 3306 인바운드 허용 (서버 PC `192.168.0.104`만) | 필수 | — |
| 3 | 고정 IP 지정, 절전 모드 끄기 | 필수 | — |
| 4 | `posture_app` 데이터베이스와 테이블 생성 (`posture_app_schema.sql`) | 필수 | — |
| 5 | `posture_app` 계정 생성과 권한 부여 | 필수 | — |
| 6 | `max_connect_errors = 10000` | 필수 | 즉시 적용 |
| 7 | `innodb_flush_log_at_trx_commit = 2` | 필수 | 즉시 적용 |
| 8 | `innodb_buffer_pool_size ≥ 256M`, `sync_binlog = 0` | 권장 (D-17) | 즉시 적용 |
| 9 | 시간대 확인 (UTC/KST) | 필수 | — |
| 10 | 접속 정보를 BE에 전달 (IP·포트·계정. **비밀번호는 메신저 개인 메시지로**) | 필수 | — |

V1.1 `posture_service`는 지금처럼 그대로 두면 됩니다. 이 가이드는 **같은 MySQL 서버에 `posture_app`을 추가**하는 내용입니다.

---

## 1. 사전 확인

```sql
SELECT VERSION();                    -- 8.0.x 이상 권장 (테스트 DB: 8.0.25)
SHOW VARIABLES LIKE 'character_set_server';   -- utf8mb4 권장
SHOW VARIABLES LIKE 'default_authentication_plugin';  -- caching_sha2_password (8.0 기본)
```

- 아래 설정은 `root` 같은 관리자 계정으로 실행합니다.
- 설정 파일 위치는 다음과 같습니다(이하 `my.ini`로 부름).
  - Windows: `C:\ProgramData\MySQL\MySQL Server 8.0\my.ini`
  - Linux: `/etc/mysql/mysql.conf.d/mysqld.cnf` 또는 `/etc/my.cnf`

## 2. 네트워크 (외부 접속 허용)

### 2.1 bind-address

기본값 `127.0.0.1`이면 같은 PC에서만 접속할 수 있습니다. `my.ini`의 `[mysqld]`에 다음을 넣습니다.

```ini
[mysqld]
bind-address = 0.0.0.0
```

수정한 뒤 MySQL 서비스를 재시작합니다.
- Windows: `services.msc` → `MySQL80` → 다시 시작
- Linux: `sudo systemctl restart mysql`

### 2.2 방화벽

Windows Defender 방화벽에서 **인바운드 규칙 → 새 규칙 → 포트 → TCP 3306 → 연결 허용 → 개인 프로필**을 만듭니다.

테스트 DB는 개인 프로필 전체를 열어 두었습니다. 새 DB는 **원격 IP를 서버 PC `192.168.0.104`로 제한**하기를 권장합니다(규칙 속성 → 범위 → 원격 IP 주소).

관리자 PowerShell로 한 번에 만들 수도 있습니다.

```powershell
New-NetFirewallRule -DisplayName "MySQL 3306 from posture server" `
  -Direction Inbound -Protocol TCP -LocalPort 3306 `
  -RemoteAddress 192.168.0.104 -Profile Private -Action Allow
```

> 네트워크 프로필이 "공용"으로 잡혀 있으면 규칙이 적용되지 않습니다. 설정 → 네트워크 → 속성에서 "개인 네트워크"로 바꿉니다.

### 2.3 고정 IP·절전

- 서버는 `.env`의 `DB_HOST`에 적힌 IP로 접속합니다. IP가 바뀌면 서버가 DB에 붙지 못합니다. 공유기 DHCP 예약이나 고정 IP로 IP를 고정합니다.
- 테스트 중 문서상 IP(`192.168.0.42`)와 실제 IP(`192.168.0.105`)가 달랐던 적이 있습니다. 확정된 IP를 꼭 알려 주세요.
- Windows 절전/최대 절전을 "안 함"으로 둡니다. PC가 잠들면 서버의 readiness가 DOWN이 됩니다.

## 3. 데이터베이스·계정

### 3.1 `posture_app` 생성

저장소(`dockerized-bigdata-env`)의 `mysql/posture_app_schema.sql`을 MySQL Workbench에서 실행합니다(File → Open SQL Script → Execute ⚡).

- 생성되는 것: 데이터베이스 `posture_app` (utf8mb4 / utf8mb4_0900_ai_ci)
- 테이블 5개: `accounts`, `baseline_postures`, `sessions`, `collapse_events`, `period_stats`
- `IF NOT EXISTS`로 작성되어 있어 여러 번 실행해도 안전합니다.

> 저장소 `README_MySQL_구축_가이드.md` A-1의 `posture_research`(연구 DB)는 **만들지 않습니다**. 연구 DB는 제거되었습니다(DN-20, V1.1 BR-58).

### 3.2 계정과 권한

```sql
CREATE USER IF NOT EXISTS 'posture_app'@'%' IDENTIFIED BY '<비밀번호>';
GRANT ALL PRIVILEGES ON posture_app.* TO 'posture_app'@'%';
FLUSH PRIVILEGES;
```

- 비밀번호는 문서나 저장소에 적지 않습니다. 서버 `.env`에만 넣습니다.
- 테스트 DB는 `'%'`(모든 호스트)로 열었습니다. 새 DB는 `'posture_app'@'192.168.0.104'`로 좁혀도 됩니다. 단, 이 경우 서버 IP가 바뀌면 계정을 다시 만들어야 합니다.
- 2단계 이관(V1.1 전환) 때는 `GRANT ... ON posture_service.*`를 같은 계정에 추가할 예정입니다. 지금은 필요 없습니다.

### 3.3 인증 방식 참고 (이전 장애 원인)

- MySQL 8의 기본 인증 `caching_sha2_password`는 SSL 없이 처음 접속할 때 서버의 공개키를 받아야 합니다.
- 서버 JDBC URL에 `allowPublicKeyRetrieval=true`가 없어서 접속이 전부 실패한 적이 있습니다. 실패가 쌓여 **호스트가 차단**되기도 했습니다(9/29 A-02, 10/05 T-11).
- 지금 서버 코드는 이 옵션을 넣어 해결했으므로 **DB 쪽에서 인증 방식을 바꿀 필요는 없습니다**(`mysql_native_password`로 바꾸지 않아도 됨).

## 4. 서버 변수

모든 항목은 `SET PERSIST`로 적용합니다. 그러면 바로 반영되고, 재시작 후에도 유지됩니다(`mysqld-auto.cnf`에 저장).
`my.ini`로 관리하고 싶다면 아래 "my.ini 대응"을 쓰고 재시작합니다. 두 방식을 섞으면 `SET PERSIST` 값이 우선합니다.

### 4.1 필수 (테스트 DB에 적용된 값)

| 변수 | 값 | 기본값 | 이유 |
|---|---|---|---|
| `max_connect_errors` | `10000` | 100 | 접속 실패가 100번 쌓이면 서버 PC가 통째로 차단되어 `FLUSH HOSTS` 전까지 접속할 수 없음. 재시작·인증 오류 때 실제로 차단됨(D-11, DN-26) |
| `innodb_flush_log_at_trx_commit` | `2` | 1 | 커밋마다 디스크 flush를 하지 않고 1초마다 함. 메시지마다 DB에 쓰는 구조라 처리량이 크게 오름(D-15, DN-27). OS가 비정상 종료되면 최대 약 1초분 기록이 사라질 수 있음 → 판정 원본은 Kafka에 남아 있어 허용 |

```sql
SET PERSIST max_connect_errors = 10000;
SET PERSIST innodb_flush_log_at_trx_commit = 2;
```

my.ini 대응:

```ini
[mysqld]
max_connect_errors = 10000
innodb_flush_log_at_trx_commit = 2
```

### 4.2 권장 (테스트 DB에는 아직 미적용 — ToDo D-17)

용량 테스트(T-11) 결과, 실시간 판정의 한계(동시 12명, 초당 약 105~110건)는 **DB 쓰기 대기** 때문이었습니다. 테스트 DB의 값은 다음과 같았습니다.

| 변수 | 테스트 DB 값 | 권장 | 이유 |
|---|---|---|---|
| `innodb_buffer_pool_size` | 8 MB (8388608) | **256M 이상** (DB 전용 PC면 메모리의 50~70%) | 데이터·인덱스 캐시. 8MB면 거의 매번 디스크를 읽음 |
| `sync_binlog` | 1 | **0** | 커밋마다 binlog를 flush함. 복제·시점 복구를 쓰지 않으면 불필요 |
| `log_bin` | ON | (그대로) | 끄려면 재시작 필요. `sync_binlog=0`으로 충분 |

```sql
SET PERSIST innodb_buffer_pool_size = 268435456;  -- 256MB, 온라인 변경 가능
SET PERSIST sync_binlog = 0;
```

- 새 DB의 기본값이 이미 더 크면(예: Windows 설치 마법사가 메모리 기준으로 잡은 경우) 그대로 두어도 됩니다.
- `DB_V1.1_검토의견.md` 3.2의 `input_result` 입력마다 쓰기 구조를 채택한다면 이 항목은 사실상 필수입니다.

### 4.3 확인만 (바꾸지 않음)

| 변수 | 테스트 DB 값 | 서버 쪽 기준 |
|---|---|---|
| `max_connections` | 151 | 서버 연결 풀 최대 8개 + 관리 도구. 충분함 |
| `wait_timeout` | 28800 (8시간) | 서버가 연결을 30분마다 교체하고 5분마다 keepalive를 보냄. 이보다 짧게 줄이지 말 것 |
| `skip_name_resolve` | OFF | ON으로 바꾸면 접속이 빨라짐. 단, 그러면 계정의 호스트를 IP로만 지정해야 함. 선택 사항 |

## 5. 데이터 이전

- 테스트 DB의 데이터는 부하 테스트로 만든 것이라 **옮길 필요가 없습니다**. 새 DB는 빈 테이블로 시작합니다.
- 보관이 필요하면 테스트 DB PC에서 다음과 같이 받아 둡니다.

```bash
mysqldump -u root -p --single-transaction --routines posture_app > posture_app_test_backup.sql
```

## 6. 이관 후 검증

### 6.1 DB 쪽 (DB 담당)

```sql
SHOW DATABASES;                                  -- posture_app, posture_service 둘 다 보여야 함
SHOW TABLES FROM posture_app;                    -- 5개
SHOW GRANTS FOR 'posture_app'@'%';
SHOW VARIABLES WHERE Variable_name IN
  ('bind_address','max_connect_errors','innodb_flush_log_at_trx_commit',
   'innodb_buffer_pool_size','sync_binlog','time_zone','system_time_zone');
```

### 6.2 서버 쪽 (BE가 진행)

1. 서버 PC에서 포트 확인: `nc -zv <새 DB IP> 3306`
2. 서버 `.env` 수정. 바꾸는 것은 `DB_HOST`뿐이고, 계정을 새로 정했다면 `DB_USER`·`DB_PASSWORD`도 바꿉니다.
   ```dotenv
   DB_HOST=<새 DB IP>
   DB_PORT=3306
   DB_NAME=posture_app
   DB_USER=posture_app
   DB_PASSWORD=<.env에만 기록>
   ```
3. `docker compose up -d api-server` 후 readiness 확인:
   `curl -s localhost:8080/actuator/health/readiness` → `db`가 `UP`
4. T-10 재생으로 기록 확인:
   ```bash
   python3 mysql/replay_posture_pilot_csv.py --file mysql/posture-pilot-P01.csv --live-timestamps
   ```
   → `sessions`에 1행, `collapse_events`에 이벤트가 생기는지 확인
   > `--live-timestamps`는 T-11 도구 패치에 들어 있습니다. 아직 병합 전이면 이 옵션을 빼고, `rebase_csv_to_now.py`로 시각을 보정한 `posture-pilot-P01-now.csv`를 씁니다.
5. 접속 차단이 없는지 확인:
   ```sql
   SELECT IP, COUNT_HANDSHAKE_ERRORS, COUNT_AUTHENTICATION_ERRORS
     FROM performance_schema.host_cache;
   ```

### 6.3 시간대 확인 (중요)

서버의 JDBC 설정이 `serverTimezone=Asia/Seoul`이라, 시각이 **한국 시각으로 저장되는지** 확인이 필요합니다. 세션 만료 쿼리는 `UTC_TIMESTAMP()`와 비교하므로, 한국 시각으로 저장되면 세션이 9시간 늦게 만료됩니다.

6.2의 재생 직후 실행합니다.

```sql
SELECT session_id, last_seen_at, UTC_TIMESTAMP(3) AS utc_now, NOW(3) AS db_now
  FROM posture_app.sessions
 ORDER BY last_seen_at DESC LIMIT 3;
```

| 결과 | 판단 |
|---|---|
| `last_seen_at` ≈ `utc_now` | 정상 (UTC 저장) |
| `last_seen_at` ≈ `utc_now` + 9시간 | 한국 시각으로 저장됨 → BE가 서버 설정을 UTC로 수정(신규 ToDo) |

같은 이유로, 새 DB 서버의 시간대 설정(`time_zone`)은 `SYSTEM`이든 `+09:00`이든 상관없습니다. **값은 UTC로 저장한다**는 원칙만 V1.1 명세에 적어 주세요(검토의견 요청 #3).

## 7. 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| `Communications link failure` / `nc` 실패 | bind-address, 방화벽, IP 변경, 절전 | 2장 다시 확인 |
| `Host '...' is blocked because of many connection errors` | `max_connect_errors` 초과 | `FLUSH HOSTS;` (8.0.23+는 `TRUNCATE performance_schema.host_cache;`) 후 4.1 적용 |
| `Public Key Retrieval is not allowed` | JDBC 옵션 누락 | 서버 쪽 문제. BE에 알려 주세요(현재 코드는 해결됨) |
| `Access denied for user 'posture_app'@'...'` | 계정 호스트 범위, 비밀번호 | 3.2의 호스트와 서버 IP 확인 |
| readiness `db` DOWN, 나머지 UP | DB 응답 없음 | 2.3 절전·IP 확인 |
