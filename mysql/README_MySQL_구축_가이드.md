# MySQL 구축 가이드 (외부 PC + Docker 연결)

**역할 분리 (2026-09-27 변경)**: 로컬 MySQL Workbench에 DB 생성 권한이
없어서, DB 자체는 **담당자가 같은 LAN(공유기) 안의 별도 PC에서
구축**하고, 우리(Docker/스크립트 쪽)는 **연결만** 하는 방향으로
바꿨다. 이 문서는 그래서 두 부분으로 나뉜다.

- **A. 담당자가 할 일** — MySQL 서버 설치, DB/계정 생성, 원격 접속 허용.
  이 폴더의 `posture_app_schema.sql` / `posture_research_schema.sql`과
  이 문서의 A절을 그대로 전달하면 된다.
- **B. 우리가 할 일** — VM 네트워크가 그 PC에 닿게 만들고, `.env`에
  IP만 채운 뒤 접속을 확인한다. DB를 만들 필요는 없다.

담당자 작업이 끝나기 전까지는 B절의 `test_db_connection.py`로
"아직 연결이 안 되는지 / 이제 됐는지"만 반복 확인하면 된다 — 스키마를
직접 만들 필요가 생기지 않는다.

---

## 0. 전체 그림 (같은 LAN, 다른 물리 PC)

```
[VirtualBox VM, Docker]              [외부 PC, 같은 공유기]
  docker-compose (kafka/redis/hdfs/    MySQL Server (3306)
   spark/api-server/inference-         MySQL Workbench(담당자용 GUI)
   service/posture-cep)
        │
        │  DB_HOST=<외부 PC의 LAN IP>:3306
        └──────────────────────────────────────────▶
```

기존 가이드(직전 버전)는 "Docker를 돌리는 VM"과 "MySQL이 있는 PC"가
**같은 물리 PC**라고 가정하고, VirtualBox의 **Host-only** 어댑터
(예: `192.168.56.1`)로 VM에서 그 PC 자신에게 접속하는 구조였다.

지금은 MySQL이 **다른 물리 PC**에 있으므로 이 가정이 깨진다.
Host-only 어댑터는 "이 VM ↔ 이 VM을 돌리는 물리 PC" 사이에만
존재하는 사설망이라, 같은 공유기에 물려 있는 **다른** PC와는 전혀
통신할 수 없다 — 여기가 이번에 반드시 고쳐야 하는 지점이다(1절).

---

## A. 담당자가 할 일 (DB 구축)

### A-1. 두 DB 만들기

MySQL Workbench에서 로컬 MySQL Server(권한 있는 계정)에 접속한 뒤:

1. `File > Open SQL Script...` → `posture_app_schema.sql` 선택 →
   Execute(⚡). `posture_app` DB + `accounts`/`baseline_postures`/
   `sessions`/`collapse_events`/`period_stats` 5개 테이블 생성.
2. 같은 방식으로 `posture_research_schema.sql` 실행. `posture_research`
   DB + `participants`/`collection_sessions`/`posture_samples`/
   `dataset_splits`/`model_evaluations` 5개 테이블 생성.

두 스크립트 모두 `CREATE ... IF NOT EXISTS`라서 여러 번 실행해도
안전하다.

### A-2. 접속 계정 만들기

```sql
-- api-server/posture-cep(Docker)이 posture_app에만 쓸 계정.
-- '%'는 "어떤 호스트에서 접속해도 허용" — VM의 IP가 매번 바뀔 수 있어
-- 특정 IP로 좁히지 않는다(테스트 환경 기준. 나중엔 VM이 속한
-- 서브넷으로 좁히는 걸 권장).
CREATE USER IF NOT EXISTS 'posture_app'@'%' IDENTIFIED BY 'changeme';
GRANT ALL PRIVILEGES ON posture_app.* TO 'posture_app'@'%';

-- 연구DB 적재 스크립트용 계정.
CREATE USER IF NOT EXISTS 'posture_research'@'%' IDENTIFIED BY 'changeme';
GRANT ALL PRIVILEGES ON posture_research.* TO 'posture_research'@'%';

FLUSH PRIVILEGES;
```

### A-3. 외부(같은 LAN) 접속 허용

기본 설치된 MySQL은 `bind-address = 127.0.0.1`(자기 자신에서만 접속
허용)로 잠겨 있다. 같은 LAN의 다른 PC(VM)에서 접속하려면:

**1) bind-address 열기** — MySQL 설정 파일(Windows:
`C:\ProgramData\MySQL\MySQL Server 8.0\my.ini`, macOS/Linux:
`/etc/my.cnf` 또는 `/etc/mysql/mysql.conf.d/mysqld.cnf`):

```ini
[mysqld]
bind-address = 0.0.0.0
```

수정 후 MySQL 서비스 재시작(Windows: 서비스 관리자에서 `MySQL80`
재시작 / macOS: `brew services restart mysql` / Linux:
`sudo systemctl restart mysql`).

**2) 방화벽에서 3306 포트 허용** — Windows 방화벽 인바운드 규칙에
TCP 3306 허용(사설망/홈 네트워크 프로필), macOS는 시스템 설정 >
개인정보 보호 및 보안 > 방화벽에서 허용.

**3) 이 PC의 LAN IP 확인 후 우리 쪽에 전달** — Windows: `ipconfig`의
"IPv4 주소"(예: `192.168.0.42`), macOS/Linux: `ip addr` 또는
`ifconfig`. **이 IP + 계정/비밀번호를 우리(Docker 쪽)에 전달하면
담당자 작업은 끝.**

### A-4. (선택, 미리 해두면 좋음) `max_allowed_packet` 늘리기

`posture_research.posture_samples`는 한 행에 MediaPipe Pose
33-keypoint 원본(`landmarks_json`/`world_landmarks_json`)이 그대로
들어가서 행 하나가 약 7~8KB로 일반 테이블보다 훨씬 무겁다. MySQL은
기본적으로 한 번에 보낼 수 있는 패킷 크기(`max_allowed_packet`)에
제한이 있어서, 대량 CSV를 큰 배치로 적재할 때
`Got a packet bigger than 'max_allowed_packet' bytes` 오류가 날 수
있다(실제로 15-3절 대용량 테스트에서 겪음).

MySQL 콘솔에서 즉시(재시작 없이) 적용:

```sql
SET GLOBAL max_allowed_packet = 67108864;  -- 64MB
```

영구 적용(재시작 필요) — 설정 파일(A-3의 `my.ini`/`mysqld.cnf`)에:

```ini
[mysqld]
max_allowed_packet = 64M
```

이걸 미리 해두면 우리 쪽 적재 스크립트가 `--batch-size`를 기본값
(200)보다 크게 줘도 안전하다 — 안 해두더라도 스크립트가 기본값으로
동작은 하니 급하지 않으면 넘어가도 된다.

---

## B. 우리가 할 일 (Docker 쪽 연결)

### B-1. VM 네트워크 어댑터를 Bridged로 바꾸기 (가장 중요)

VirtualBox VM 설정 > 네트워크에서, 기존 Host-only 어댑터 대신(또는
추가로) **Bridged 어댑터**를 켠다 — 실제 LAN 카드(Wi-Fi/이더넷)를
선택하면 VM이 공유기에서 직접 IP를 받아 같은 LAN의 다른 기기(외부
PC)와 직접 통신할 수 있게 된다. Host-only만 있으면 VM은 그 물리 PC
자신하고만 통신 가능하고 공유기 너머 다른 기기는 절대 못 본다.

VM을 재시작한 뒤 VM 안에서:

```bash
ip addr show   # Bridged 어댑터가 192.168.0.x 같은 "공유기 대역" IP를 받았는지 확인
ping -c 3 <담당자 PC의 LAN IP>   # 먼저 ICMP로 도달하는지 확인 (방화벽이 ping은 막을 수도 있음 — 안 되면 바로 4번으로)
```

기존에 Host-only로 api-server ↔ 컨테이너 등 다른 용도로 쓰던 게
있다면 어댑터를 하나 더 추가(Adapter 2 = Bridged)하는 쪽이 안전하다
— 기존 구성을 건드리지 않고 외부 PC로 가는 경로만 새로 연다.

### B-2. `.env`에 담당자가 알려준 IP 채우기

```dotenv
DB_HOST=192.168.0.42      # 담당자 PC의 LAN IP (A-3에서 전달받음)
DB_PORT=3306
DB_NAME=posture_app
DB_USER=posture_app
DB_PASSWORD=changeme      # A-2에서 만든 비밀번호

RESEARCH_DB_HOST=192.168.0.42
RESEARCH_DB_PORT=3306
RESEARCH_DB_NAME=posture_research
RESEARCH_DB_USER=posture_research
RESEARCH_DB_PASSWORD=changeme
```

### B-3. 연결 확인 (담당자 작업 완료 전에도 반복 실행 가능)

Docker를 아직 띄우지 않아도, VM에서 바로 확인할 수 있다 — **DB를
만들 필요 없이 접속만** 확인하는 스크립트다.

```bash
cd mysql

# venv(.venv 등)로 패키지를 관리 중이면 먼저 활성화하고 일반 설치:
#   source ../.venv/bin/activate  (경로는 실제 venv 위치에 맞게)
#   pip install -r requirements.txt
# venv 없이 시스템 파이썬에 바로 설치할 때만 --break-system-packages 필요:
#   pip install --break-system-packages -r requirements.txt

# .env 하나로 서비스DB/연구DB 둘 다 확인
python3 test_db_connection.py --env-file ../.env
```

단계별로 무엇을 보게 되는지:

| 상황 | 출력 |
|---|---|
| VM이 아직 Bridged가 아니거나 방화벽이 막혀 있음 | `Can't connect ... (timed out)` — B-1/A-3 다시 확인 |
| 네트워크는 되는데 계정/비밀번호가 다름 | `Access denied for user` — A-2 다시 확인 |
| 접속은 되는데 담당자가 아직 DB를 안 만듦 | `Unknown database 'posture_app'` — 담당자 작업 대기 |
| 접속되고 DB도 있는데 테이블이 없음 | "테이블 없음" 메시지 — 담당자가 A-1(스키마 스크립트)을 아직 안 돌림 |
| 전부 정상 | MySQL 버전 + 테이블 목록 출력 |

### B-4. api-server / posture-cep 기동

접속이 확인되면 `docker-compose.yml`이 있는 디렉토리에서:

```bash
docker compose up -d --build api-server posture-cep
curl -s http://localhost:8080/actuator/health | python3 -m json.tool
```

`components.db.status`가 `UP`이면 성공. 이후 절차(CSV 적재/부하
테스트)는 `README_빅데이터플랫폼_실행가이드.md` 15절 그대로 진행하면
된다 — DB 접속 정보만 바뀌었을 뿐 스크립트 사용법은 동일하다.

---

## 문제 해결 체크리스트

| 증상 | 원인 후보 | 확인 |
|---|---|---|
| `ping`도 안 되고 `test_db_connection.py`도 타임아웃 | VM이 여전히 Host-only만 쓰고 있음 | VirtualBox 설정에서 어댑터가 Bridged인지, VM 재시작 후 `ip addr`로 공유기 대역 IP를 받았는지 확인 |
| `ping`은 되는데 3306만 안 됨 | 담당자 PC 방화벽이 3306을 막음 | A-3 2)번 다시 확인 — Windows는 "사설망" 프로필에서 허용해야 함(공용망 프로필만 허용하면 무용) |
| `Access denied for user 'posture_app'@'172.x.x.x'` | 컨테이너 출발 IP가 Bridged VM의 IP가 아니라 Docker의 내부 bridge망(172.x) IP로 나가서, 계정이 `'posture_app'@'%'`가 아니라 특정 호스트로 좁혀져 있었을 때 | `'posture_app'@'%'`로 만들었는지 재확인(A-2) — Docker 컨테이너는 보통 NAT을 거쳐 VM의 IP로 나가므로 실제로는 문제되지 않지만, VM 자체에 여러 네트워크 인터페이스가 있으면 출발 IP가 예상과 다를 수 있음 |
| `Public Key Retrieval is not allowed` | MySQL 8 기본 인증 플러그인(`caching_sha2_password`)과 드라이버 설정 불일치 | api-server의 JDBC URL에 `allowPublicKeyRetrieval=true` 추가 (테스트 환경 한정, 운영에서는 SSL 사용 권장) |
| Workbench(담당자 PC)로는 잘 되는데 VM에서만 안 됨 | 십중팔구 B-1(Bridged 전환) 누락 | `ip addr`로 VM이 실제로 공유기 대역 IP를 받았는지부터 확인 |