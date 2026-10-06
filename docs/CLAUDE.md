# CLAUDE.md — Claude 작업 지침

> 이 문서는 **새 대화(세션)를 시작한 Claude가 가장 먼저 읽는 문서**다.
> 이전 대화 내용이 남아 있지 않아도, 이 문서와 아래 "읽는 순서"의 문서만 읽으면
> 프로젝트가 무엇이고, 지금 어디까지 왔고, 다음에 무엇을 해야 하는지 알 수 있어야 한다.
>
> 최종 갱신: 2026-10-06 (우선순위 척도 1=가장 시급/중요 ~ 5=낮음 고정, 문서 저장 규칙 추가)

---

## 0. 세션 시작 시 할 일 (반드시 이 순서로)

1. **이 문서(CLAUDE.md)** — 규칙·고정 결정·명령어
2. **`ToDo_리스트.md`** — 작업 현황판. 지금 열려 있는 항목(Development/Test/ToDo)과 우선순위 확인
3. **`프로젝트_현황_및_다음단계.md`** — 작업 ID별 상세 기록(어떻게 했고 결과가 무엇이었는지). 손댈 항목의 기록을 먼저 읽는다
4. **`PRD.md`** — DevOps/BE가 만족해야 하는 요구사항과 수용 기준
5. **아키텍처 문서** — `자세 분석 플랫폼 아키텍처 v4.html` / `.md` (요약·다이어그램),
   세부 명세는 `Posture_Architecture_v4.md`, 메시지 계약은 `Kafka_메시지_규격_v1.md`

사용자가 "이어서 하자", "다음 작업" 같이 말하면 위 2·3번을 근거로 **다음 후보 작업을 제안하고 확인을 받은 뒤** 착수한다.

---

## 1. 사용자와 담당 범위

- 사용자는 6인 팀에서 **DevOps / BE 담당**이다.
- Claude가 다루는 범위도 **DevOps / BE**로 한정한다.
  - 포함: 서버 PC 인프라, Docker Compose, Kafka·Redis·HDFS·Spark 운영, Spring Boot API 서버, 상태머신, DB 연동, CI/CD, K8s 이전, 부하·검증 테스트
  - 제외(다른 담당자): 프론트엔드(React) 구현, LSTM 학습·평가, ABA 파일럿 실험, 라벨링 실행
- 제외 범위 작업은 ToDo 리스트에 올리지 않는다. 필요하면 "제외된 항목" 표에 기록만 남긴다.

---

## 2. 작업 진행 규칙 (가장 중요)

1. **ToDo 리스트에 올라온 항목만 진행한다.** (ToDo/Analysis/Development/Test 섹션)
2. 테스트·분석 중 **새 이슈를 발견하면 바로 고치지 않는다.** 먼저 ToDo 리스트에 새 ID로 등록하고,
   사용자의 우선순위 지시를 받은 뒤 착수한다. (예: D-15는 발견 후 등록만 하고 착수 보류 중)
3. 작업 ID는 상태가 바뀌어도 유지한다. 완료 시 Done 섹션으로 옮기며 `DN-xx` 번호를 붙이고 원래 ID를 비고에 남긴다.
4. **작업이 끝나면 문서 두 개를 반드시 갱신한다.**
   - `ToDo_리스트.md`: 항목 상태 이동 + 최상단에 날짜별 갱신 메모
   - `프로젝트_현황_및_다음단계.md`: 해당 ID 섹션에 **배경 / 작업 방법 / 결과 / 근거** 기록
   - 팀 결정이 바뀐 경우에만 PRD·계획서·아키텍처 문서에 필요한 부분을 반영
5. **"Done"의 기준은 실측 검증이다.** 코드를 만들었다고 Done이 아니다.
   사용자가 서버 PC에서 적용·실행하고 결과(로그·API 응답·DB 조회)를 확인해야 Done.
6. 사용자가 서버 PC에서 직접 실행한다. Claude는 **패치/파일 + 적용 명령어 + 확인 방법(기대 결과)** 을 함께 전달한다.
7. 측정·검증은 **깨끗한 상태**에서 한다. 처리량 측정 전에는 대상 서비스 재시작 + 컨슈머 offset 리셋(DN-25 교훈).
8. 이전 수치를 재사용할 때는 **어떤 경로 기준 수치인지** 확인한다.
   (예: DN-10의 730 req/sec는 REST 수집량이지 실시간 처리량이 아니다.)
9. **우선순위 척도는 1(가장 시급/중요) ~ 5(낮음)** 이다. 숫자가 작을수록 먼저 처리한다.
   ToDo 리스트·현황 문서의 모든 우선순위 숫자와 새로 등록하는 항목에 이 척도를 쓴다. (2026-10-06 사용자 지시로 기존 "1=낮음 ~ 5=가장 중요"에서 변경, 기존 숫자는 6−값으로 반전)
10. **프로젝트 문서를 저장(덮어쓰기)할 때는 반드시 프로젝트의 최신본을 먼저 읽고 그 위에 수정한다.**
    세션 시작 때 읽은 사본이나 이전 대화의 사본을 그대로 다시 쓰면 다른 세션의 변경이 사라진다.
    (2026-10-06: 우선순위 척도 정정이 다른 세션의 T-11 완료 저장으로 한 번 되돌아갔음)

---

## 3. 고정된 결정 (바꾸려면 팀 결정이 필요)

| 구분 | 결정 | 근거 |
|---|---|---|
| 범위 | 현재 자세의 **이진 분류(good/bad)** 만 한다. 붕괴 시점 **예측은 범위 밖** — 문서·코드 용어도 "분류"로 통일 | 계획서 |
| 개인정보 | 서버로는 **키포인트 좌표만** 전송. 원본 영상·이미지는 어떤 계층(Kafka/HDFS/MySQL/학습셋)에도 두지 않는다 | 계획서, 아키텍처 1.2 |
| 빅데이터 구성 | **Kafka · Redis · HDFS · Spark 4종 고정**. 새 인프라 추가 금지 (Esper, Zeppelin, Kafka Connect, Eureka, Config Server 모두 배제) | v4 D7, DN-18 |
| 실시간 판정 | Esper(CEP) 미도입. **상태머신**으로 판정, `api-server`의 `com.posture.api.posture.cep` 패키지에 구현 | DN-18, DN-23 |
| 경로 분리 | HDFS·Spark는 **실시간 경로에 넣지 않는다**. DB를 메시지 큐로 쓰지 않는다 | v4 D2, D3 |
| 서비스 간 통신 | 동기 REST는 FE→gateway→서비스만. **서비스↔서비스는 Kafka 이벤트만** | v4 설계원칙 3 |
| MySQL | **컨테이너화하지 않고 외부**에 둔다. 컨테이너는 IP:3306으로 접속, 재시도 로직 필수 | v4 D6 |
| 추론 서비스 | 최종 위치는 **외부 GPU PC**. Kafka `9094`로만 접속 (Redis·MySQL 접근 없음) | v4 D5, D9 |
| 연구 데이터 | 연구DB 제거 완료. 연구용 데이터는 **CSV 파일로만** 수집 | DN-20 |
| BE 구조 | 모듈러 모놀리스(`user`/`realtime`/`report` 패키지) → 2단계-B에서 MSA 분리 | v4 D8 |
| 상태머신 파라미터 | **현재 구현값 T1=3초 / T2=3초 / T3=60초 잠정 유지**. v4 문서 초안값(10/5/60)은 팀 회의 확정 전 | DN-22 |
| 일정 | **개발은 11월 안에 종료**, 12월은 유지보수·시연 준비만(신규 개발 없음) | 계획서 |
| 이미지 | Bitnami 이미지 사용 금지(2025년 무료 태그 정책 변경으로 버전 태그 소멸). 공식 `apache/kafka`, `apache/spark` 사용, **버전 태그 고정** 지향 | 구축 기록 |

---

## 4. 실행 환경

| 장비 | 주소 | 역할 |
|---|---|---|
| 서버 PC | `192.168.0.104` (Ubuntu Server, 6C/12T, 16GB, 500GB) | Docker Compose로 api-server, inference-service(임시), Kafka, Redis, HDFS, Spark 실행 |
| 외부 GPU PC | `192.168.0.108` | 모델 담당자 환경. inference-service 최종 이전 대상(방화벽 설정 완료, 서비스 이전은 미완) |
| 외부 MySQL | `.env`의 접속 정보 사용 | 서비스DB `posture_app` (테이블: `accounts`, `baseline_postures`, `collapse_events`, `period_stats`, `sessions`) |

- 코드 저장소: GitHub `dockerized-bigdata-env` (서버 PC에 clone 해서 사용)
- 비밀값(DB 계정 등)은 `.env`에만 두고 Git에 올리지 않는다. Claude는 실제 비밀값을 문서에 적지 않는다.

### 현재 컨테이너 구성 (2026-10-04)

| 컨테이너 | 내용 |
|---|---|
| `api-server` | Spring Boot 4.0.8. 수집 API `/api/v1/posture/summary` → Kafka `posture.summary` 발행. CEP 컨슈머(그룹 `api-server-cep`)가 `posture.inference` 소비 → 상태머신 → `sessions`/`collapse_events` 기록 |
| `inference-service` | Python. `posture.summary` 소비 → 규칙/테스트 LSTM 추론 → `posture.inference` 발행 (합성 데이터 학습 테스트 모델) |
| `kafka` | `apache/kafka` KRaft 단일 브로커. 리스너: `kafka:19092`(컨테이너 간), `127.0.0.1:9092`(호스트), `EXTERNAL 9094`(GPU PC 전용) |
| `redis` | `127.0.0.1:6379`. 헬스체크만 연결됨, 실제 상태 저장은 미구현(D-04) |
| `namenode` / `datanode` | HDFS. WebHDFS 9870/9864는 GPU PC IP로만 허용 |
| `spark` | `apache/spark`, `local[*]` 상주 컨테이너(`tail -f /dev/null`), UI `127.0.0.1:4040` |
| `posture-sink` | Spark Structured Streaming, `posture.summary` → HDFS 10초 마이크로배치 |

> v4 목표 구조(토픽 5종, WebSocket, realtime/user/report 분리, Spark J1~J3)와의 차이는 `PRD.md`와 현황 문서의 "갭" 표를 본다.

---

## 5. 자주 쓰는 명령어 (서버 PC, 저장소 루트 기준)

```bash
# 기동 / 상태 / 로그
docker compose up -d --remove-orphans
docker compose ps
docker logs -f api-server
docker compose restart api-server inference-service
docker compose build --no-cache <서비스명>      # 코드 변경 후 재빌드

# 헬스체크 (db, redis 모두 UP이어야 함)
curl -s http://localhost:8080/actuator/health

# Kafka
K="docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092"
$K --list
docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group api-server-cep      # lag 확인
docker exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --group api-server-cep \
  --reset-offsets --to-latest --all-topics --execute                       # 측정 전 offset 리셋(컨슈머 정지 상태에서)

# 상태머신(CEP) 확인용 API
curl -s http://localhost:8080/cep/active
curl -s http://localhost:8080/cep/events/recent
curl -s -X POST http://localhost:8080/cep/sessions/expire

# 테스트 데이터 재생
python3 generate_collapse_test_csv.py                  # 정상5s+나쁜자세70s+회복10s, 850행
python3 replay_posture_pilot_csv.py --pace realtime    # 실시간 속도 재생 (--pace fast: 최대 속도)

# MySQL 호스트 차단 해제 (Host '...' is blocked 발생 시)
mysqladmin -h <MySQL IP> -u <계정> -p flush-hosts
```

> 스크립트의 정확한 경로·옵션은 저장소의 `README_빅데이터플랫폼_실행가이드.md`를 따른다.
> 이 표의 명령이 저장소와 다르면 저장소 쪽이 맞고, 이 문서를 고친다.

---

## 6. 코딩 표준

### 공통
- 설정값(주소, 포트, 계정, 상태머신 파라미터)은 **환경변수**로 받는다. 코드에 IP·비밀번호를 하드코딩하지 않는다. (K8s 이전 시 ConfigMap/Secret으로 그대로 옮기기 위함)
- 로그는 상태 전이·에러·외부 연결 실패를 반드시 남긴다. 검증은 로그·API·DB **세 곳이 일치**하는지로 판단한다(DN-24 방식).
- 시간은 **UTC epoch milliseconds**(Kafka 규격) 또는 UTC `DATETIME(3)`(DB). 로컬 시간 사용 금지.

### Java / Spring Boot (`api-server`)
- 패키지 루트 `com.posture.api`. 상태머신은 `com.posture.api.posture.cep`.
- 2단계-A 이후 신규 코드는 `user` / `realtime` / `report` 패키지 경계를 지킨다.
  다른 패키지의 클래스·Repository를 직접 호출하지 않고 Kafka 이벤트로 받는다. 패키지별 담당 테이블 외 조회 금지.
- Kafka: `Kafka_메시지_규격_v1.md` 준수
  - Producer `acks=all`, `enable.idempotence=true`, `compression.type=lz4`, `linger.ms=5`, key=`userId`
  - Consumer `enable.auto.commit=false`(처리 후 커밋), `eventId` 기준 멱등 처리, 3회 재시도 후 `posture.dlq`
  - Jackson `FAIL_ON_UNKNOWN_PROPERTIES=false` (모르는 필드는 무시)
- DB 쓰기는 메시지마다 개별 커밋하지 않도록 설계한다(D-15 병목의 원인). 배치/트랜잭션 묶음/주기적 쓰기를 우선 고려.
- 테스트: 로직 변경 시 **JUnit 테스트 필수**. 기존 동작을 옮길 때는 원본 테스트 시나리오를 전부 재현(DN-23: pytest → JUnit 12개).

### Python (`inference-service`, 스크립트)
- `confluent-kafka` 사용, 접속 주소는 환경변수. 테스트는 `pytest`.
- 폐기된 스크립트는 삭제하지 않고 `archive/` 디렉터리로 옮긴다(예: `mysql/archive/`, `archive-posture-cep/`).

### Docker / 인프라
- 모든 서비스: `restart: unless-stopped`, `mem_limit` 명시, 로그 회전(`max-size 10m`, `max-file 3`).
- 포트 바인딩: 내부 전용은 `127.0.0.1:`로. GPU PC 전용(9094/9870/9864)은 서버IP 바인딩 + `DOCKER-USER` 체인 제한.
  **Docker가 연 포트는 ufw를 우회한다**는 점을 항상 고려한다.
- 추론 서비스는 Dockerfile + requirements.txt를 유지한다(GPU PC 장애 시 서버 PC CPU 대체 실행용).

---

## 7. 알려진 함정 / 교훈

- **처리량 한계는 REST가 아니라 CEP 컨슈머에 있다.** 현재 실시간 처리율 ≈ 초당 50건 고정(D-15 참고).
- MySQL `Host '...' is blocked` → `flush-hosts`로 해제, 재발 방지는 `max_connect_errors` 상향(D-11).
- `SHOW TABLES` 결과가 이상하면 `USE posture_app;`을 먼저 했는지 확인(DN-15).
- VM 시절 디스크 99%로 Kafka가 크래시한 적 있음 → 디스크·로그 회전·토픽 보존 기간을 먼저 의심.
- 한글 파일명은 셸에서 정규화 문제가 생길 수 있다 → Python `os.listdir()`/`shutil`로 다룬다.
- 프로젝트 문서는 여러 세션이 같은 파일을 통째로 덮어쓴다 → 저장 직전에 최신본을 다시 읽는다(2장 규칙 10).

---

## 8. 문서 지도

| 문서 | 역할 | 갱신 주기 |
|---|---|---|
| `README.md` | 프로젝트 소개, 구성, 설치·실행 방법 | 구성/설치 절차가 바뀔 때 |
| `CLAUDE.md` | Claude 작업 규칙, 고정 결정, 명령어, 코딩 표준 | 규칙·결정이 바뀔 때 |
| `PRD.md` | DevOps/BE 요구사항, 수용 기준 | 요구사항·팀 결정이 바뀔 때 |
| `ToDo_리스트.md` | 작업 현황판 (상태·우선순위 — 1=가장 시급 ~ 5=낮음) | **작업마다** |
| `프로젝트_현황_및_다음단계.md` | 작업 ID별 상세 기록 (방법·결과·근거), 갭, 다음 단계 | **작업마다** |
| `자세 분석 플랫폼 아키텍처 v4.html` / `.md` | 아키텍처 요약(다이어그램 포함) | 아키텍처 변경 시 |
| `Posture_Architecture_v4.md` | 아키텍처 세부 명세 | 아키텍처 변경 시 |
| `Kafka_메시지_규격_v1.md` | 서비스 간 메시지 계약 | 규격 변경 절차(9장)에 따라 |
| `전체_설계안_v4.md` | 팀 공유용 방향성·파트별 할 일·일정 | 팀 결정 시 |
| `아키텍처_v4_검토의견_2026-10-02.md` | v4 전환 검토 근거 | 이력용(수정 안 함) |
| `2026학년도_2학기_기업연계_프로젝트_계획서_v2.md` | 제출용 계획서 | 팀 결정 반영 시 |

저장소 내부 문서: `README_빅데이터플랫폼_실행가이드.md`(실행 절차), `테스트_도커_환경_구축_기록.md`(구축 상세 기록), `mysql/README_MySQL_구축_가이드.md`.
