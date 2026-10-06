# LSTM 기반 자세 붕괴 주기 분석 및 교정 보조 시스템

> 2026학년도 2학기 기업연계 프로젝트 · 6인 팀 · 연구 기간 2026-09-01 ~ 2026-12-15

웹캠으로 사용자의 앉은 자세를 실시간으로 분석해, 나쁜 자세가 일정 시간 이어지면 교정 알림을 보내는 시스템이다.
브라우저에서 추출한 **신체 키포인트 시계열**을 LSTM으로 **현재 자세 상태(good / bad)로 이진 분류**하고,
상태머신이 지속·회복·재알림 조건을 판단해 알림과 기록을 남긴다. 쌓인 데이터는 통계(ABA 리포트)와 모델 재학습에 쓴다.

- **범위 밖**: 자세 붕괴 시점의 *예측*. 본 시스템은 현재 상태의 *분류*만 수행한다.
- **개인정보 원칙**: 서버로는 키포인트 좌표만 전송한다. 원본 영상·이미지는 어떤 계층에도 저장·전송하지 않는다.

---

## 시스템 구성

```
[실시간]  브라우저(키포인트 추출) → API 서버 → Kafka → 추론 서비스(LSTM) → Kafka → 상태머신 판정 → 알림 / DB 기록
[적재]    Kafka → Spark → HDFS(Parquet) → 학습셋 생성 / MySQL 통계 마트
```

| 구성요소 | 기술 | 역할 |
|---|---|---|
| 프론트엔드 | React | 키포인트 추출, 캘리브레이션, 알림·기록 화면 |
| API 서버 | Spring Boot 4.0.8 (Java) | 수집 API, Kafka 발행, 상태머신 판정, DB 기록 |
| 추론 서비스 | Python, LSTM | 키포인트 윈도우 → good/bad 분류 |
| 메시지 버스 | Apache Kafka (KRaft, 단일 브로커) | 서비스 간 이벤트 전달, 실시간/적재 경로 분기 |
| 상태 저장 | Redis | 사용자별 판정 상태·최근 결과 |
| 장기 저장 | HDFS | 원본 키포인트·추론 결과, 학습셋, 모델 버전 |
| 배치 처리 | Apache Spark | Kafka→HDFS 적재, 학습셋 생성, 통계 집계 |
| DB | MySQL (외부) | 회원, 기준자세, 세션·에피소드 기록, 통계 마트 |
| 실행 환경 | Docker Compose → Kubernetes(2단계-B) | |

### 물리 배치

| 장비 | 실행 |
|---|---|
| 서버 PC (Ubuntu Server, 6C/12T, 16GB) | API 서버, Kafka, Redis, HDFS, Spark — Docker Compose |
| 외부 GPU PC | 추론 서비스, 학습 환경 (모델 담당) |
| 외부 MySQL | 서비스DB `posture_app` |
| 사용자 브라우저 | React 앱 |

자세한 구조는 아래 문서 표의 아키텍처 문서를 본다.

---

## 진행 단계

| 단계 | 내용 | 상태 (2026-10-04) |
|---|---|---|
| 1단계 | FE – API 서버 – 추론 서비스 – MySQL 핵심 흐름 | 서버 측 완료 |
| 2단계-A | 빅데이터 플랫폼 통합, Kafka 기반 실시간 경로, 모듈러 모놀리스 | 진행 중 — 파이프라인·상태머신 동작 검증 완료, 처리량 병목(D-15) 해소 필요 |
| 2단계-B | MSA 분리, CI/CD, K8s 멀티노드 배포 | 예정 (11월) |

개발은 11월 안에 끝내고, 12월은 유지보수·시연 준비만 한다. 현재 작업 현황은 `ToDo_리스트.md`를 본다.

---

## 설치 및 실행 (서버 PC 기준)

### 1. 사전 준비

| 항목 | 요구 사항 |
|---|---|
| OS | Ubuntu Server 24.04 LTS (고정 IP, SSH 키 인증) |
| 자원 | RAM 16GB, swap 4GB 권장, 디스크 여유 100GB 이상 |
| 소프트웨어 | Docker Engine + Docker Compose 플러그인, Git |
| 외부 의존 | 접속 가능한 MySQL 서버(`posture_app` 스키마), 같은 LAN의 GPU PC(추론 이전 시) |

Docker 설치 후 현재 사용자를 `docker` 그룹에 추가하고, 서버 재부팅 시 Docker가 자동으로 시작되도록 설정한다.

### 2. 저장소 받기

```bash
git clone <저장소 주소>/dockerized-bigdata-env.git
cd dockerized-bigdata-env
```

### 3. 환경변수 설정

저장소의 예시 파일을 복사해 `.env`를 만들고 MySQL 접속 정보 등을 채운다. `.env`는 Git에 올리지 않는다.

```bash
cp .env.example .env    # 예시 파일 이름은 저장소 기준
vi .env                 # MySQL 호스트/포트/계정, 서버 IP 등
```

MySQL은 컨테이너가 아니라 **외부 서버**다. 컨테이너는 `<MySQL IP>:3306`으로 접속한다.

### 4. 기동

```bash
docker compose up -d --remove-orphans
docker compose ps                         # 모든 컨테이너가 healthy인지 확인
curl -s http://localhost:8080/actuator/health   # db, redis 모두 UP
```

### 5. Kafka 토픽 확인

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### 6. 동작 확인 (테스트 데이터 재생)

```bash
python3 generate_collapse_test_csv.py                 # 나쁜 자세 구간이 포함된 테스트 CSV 생성
python3 replay_posture_pilot_csv.py --pace realtime   # API 서버로 재생
curl -s http://localhost:8080/cep/events/recent       # 붕괴 이벤트 기록 확인
```

정상이라면 `api-server` 로그에 이벤트 시작 → 재알림 → 종료가 순서대로 찍히고, MySQL `collapse_events`에 같은 값이 기록된다.

### 7. 종료

```bash
docker compose down          # 컨테이너만 정리 (데이터 볼륨 유지)
```

### 포트

| 포트 | 서비스 | 공개 범위 |
|---|---|---|
| 8080 | API 서버 | LAN |
| 9094 | Kafka EXTERNAL | GPU PC IP만 |
| 9870 / 9864 | HDFS WebHDFS | GPU PC IP만 |
| 9092 / 6379 / 4040 | Kafka(호스트) / Redis / Spark UI | `127.0.0.1` (서버 PC 내부) |

> Docker가 연 포트는 ufw를 우회하므로, GPU PC 전용 포트는 `DOCKER-USER` 체인으로 제한한다.
> 상세 절차·트러블슈팅은 저장소의 `README_빅데이터플랫폼_실행가이드.md`를 따른다.

---

## 문서

| 문서 | 내용 |
|---|---|
| `README.md` | 이 문서 — 프로젝트 소개, 설치·실행 |
| `CLAUDE.md` | AI 작업 지침 — 작업 규칙, 고정 결정, 명령어, 코딩 표준 |
| `PRD.md` | DevOps/BE 요구사항 명세 |
| `ToDo_리스트.md` | 작업 현황판 |
| `프로젝트_현황_및_다음단계.md` | 작업별 상세 기록(방법·결과), 남은 갭, 다음 단계 |
| `자세 분석 플랫폼 아키텍처 v4.html` / `.md` | 아키텍처 요약 (다이어그램) |
| `Posture_Architecture_v4.md` | 아키텍처 세부 명세 |
| `Kafka_메시지_규격_v1.md` | 서비스 간 메시지 계약 |
| `전체_설계안_v4.md` | 팀 공유용 방향성, 파트별 할 일, 일정 |
| `2026학년도_2학기_기업연계_프로젝트_계획서_v2.md` | 프로젝트 계획서 |

## 팀

6명 (BE·DevOps / FE / ML·모델 / 데이터 등 파트별 분담). 이 저장소의 인프라·BE는 DevOps/BE 담당이 관리한다.
