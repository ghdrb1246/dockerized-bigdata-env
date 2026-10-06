# 프로젝트 ToDo 리스트 (전체 작업 현황)

최종 갱신: 2026-10-06 (38차, 우선순위 척도 복구 — 1=가장 시급 ~ 5=낮음 / 프로젝트 문서 저장소 반영)

이 문서는 프로젝트의 모든 작업을 상태별로 관리하는 **작업 현황판**이다.
`프로젝트_현황_및_다음단계` 문서가 "지금 어디까지 왔는가"를 서술식으로
정리한 것이라면, 이 문서는 개별 작업 단위로 쪼개서 상태·우선순위를
추적하는 용도다. 추후 노션으로 옮길 예정이므로 표 구조를 그대로
유지한다.

**상태 정의**
- **ToDo**: 아직 분석도 시작 안 한 백로그
- **Analysis**: 원인 조사·요구사항 분석 진행 중
- **Development**: 설계/구현 진행 중이거나 착수 예정
- **Test**: 구현은 됐고 VM/실제 환경 검증이 필요하거나 진행 중
- **Blocked**: 외부 요인(담당자 작업, 네트워크, 팀 결정 대기 등)으로 못 움직이는 상태
- **Done**: 완료 (VM 실측 검증 완료 또는 문서/결정 반영 완료)

**우선순위**: 1(가장 시급/중요) ~ 5(낮음) — 2026-10-06 사용자 지시로 척도 변경, 기존 숫자는 6−값으로 반전

**담당 범위**: 이 문서는 **DevOps/BE 담당자** 기준으로 관리한다. FE·ML
담당자 몫인 항목(프론트엔드 구현, LSTM 학습/평가, ABA 파일럿 실험 등)은
이 문서에서 제외하고 각 담당자가 별도로 관리한다.

---

## 2026-10-04 갱신 메모 (담당 범위 조정)

DevOps/BE 담당 기준으로 문서를 정리했다. **D-08(프론트엔드 착수),
T-05(LSTM 실제 데이터 재학습), T-06(ABA 파일럿 실험)을 제거** —
각각 FE, ML 담당자 업무이고 DevOps/BE 범위가 아니다. (T-04, D-02처럼
"데이터 수집" 쪽은 DevOps/BE가 CSV 파이프라인을 지원하는 역할이 있어
남겨두되, 실제 라벨링·학습·실험 실행 자체는 해당 담당자 소관이라는 점을
구분해서 본다.)

## 2026-10-06 갱신 메모 (우선순위 척도 복구, 문서 저장소 반영)

- **우선순위 척도 복구**: 사용자 지시(1=가장 시급/중요 ~ 5=낮음, 기존 숫자 6−값 반전)가 다른 세션의 저장으로 되돌아가 있던 것을 다시 적용(CLAUDE.md 규칙 9·10).
- 프로젝트 문서 12개를 우리 저장소 `docs/`에 커밋 → PR → `main` 병합 후 팀 저장소로 이동 예정(사용자 결정). D-25의 일부.

## 2026-10-06 갱신 메모 (D-25 앞당김: 팀 저장소 이전 방법)

- 사용자 결정: **팀 저장소 이전 + 전체 검토(D-25)를 먼저** 하고 다음 작업을 정한다(D-19 완료를 기다리지 않음).
  팀 저장소에 `develop` → `DevOps` 브랜치 생성 완료, 작업은 `DevOps` 아래 작업별 브랜치로 한다.
- 이전 방법 검토 결과(제안, 사용자 확정 대기): **이력 없이 `8cb4aec` 시점 스냅샷을 하위 폴더 하나(예: `platform/`)로 복사**.
  이유: 우리 이력 첫 커밋에 참여자 CSV(`posture-pilot-P01*.csv`)·모델 가중치(`test_lstm.pt`)가 있어, 이력을 가져오면 팀 저장소 이력에 영구히 남음
  (팀 `check_repository.py`가 두 종류 모두 금지). 이력은 17커밋뿐이라 원본 저장소를 보관용으로 남기고 커밋 메시지에 출처를 적는다.
- 팀 CI(`harness.yml`, 모든 push에서 `make check`)를 통과하려면: CSV·`.pt` 제외, 모든 MD에 `- 분야:`/`- 작업: GP-xxxx` 머리말 + GP 카드,
  깨진 로컬 링크 정리(`docs/CONVENTIONS.md`는 팀 규칙으로 대체되므로 제외 제안), 우리 `.github/workflows`는 가져오지 않고 D-09에서 다시 구성.

## 2026-10-06 갱신 메모 (FE 안건 답변·서버–Kafka–프론트 연동안 검토)

- FE가 안건 답변(Q4·Q5·Q6·Q8·Q11·Q12·Q16·Q17·Q24·Q27)과 연동안(H1~H5·F1~F4·J1~J2)을 공유 → 검토의견 **`FE연동안_BE검토의견.md`** 작성.
  팀 `develop`(`41bc8dc`)에 이미 병합된 실시간 계약 초안 `contracts/realtime/`(토픽 `posture.features/inference/episodes.v1`, 키 `session_id`)도 함께 검토.
- 결론: **역할 나누기(Q1 C안) 동의** — 입구·인증·세션 시작/종료는 팀 `develop`, Kafka 뒤는 DevOps/BE, 게이트웨이는 FE.
  동의 전 결정 필요 5건: ① Kafka 메시지 단위(구간 1개 vs 0.5초 묶음 — 구간마다면 동시 4~5명 한계) ② 판정 구현 A(우리 상태머신 확장) vs B(팀 `backend/cep` Esper에 Kafka 소비 추가)
  ③ DB 쓰기 주체(판정은 DB 안 씀 → 처리량·D-18 동시 해결) ④ 이벤트 시각(`end_ms`) 기준 판정 ⑤ 내부 소비자 DLQ.
- FE 확인 요청 #5~#15에 BE 답 작성(조회 단계 불필요, 처리량, 제외 구간 가능, 알림 표시 필드, `calibration_required`, 중앙값은 원천 계산, 내부 JWT 보류 등).
- **D-21~D-24 신규 등록(미착수, 2.1·2.2 결정 전 D-22·D-23 착수 금지)**, D-14b는 D-21로 대체.
- **D-25 신규 등록(예정)**: DB 이관·시험(D-19) 마무리 후 팀 저장소로 이전(`develop` → `DevOps` → 작업별 브랜치), 이전 후 팀 저장소 전체 읽고 검토.

## 2026-10-06 갱신 메모 (DB 명세서 V1.1 검토, 새 DB 이관 준비)

- DB 담당이 다른 PC에 새 DB(명세서 V1.1, `posture_service` 26개 테이블)를 구축 완료 → 테스트 DB에서 옮기기 전 검토.
- **검토 결론(`DB_V1.1_검토의견.md`)**: V1.1에는 api-server가 쓰는 `posture_app`·`sessions`·`collapse_events`가 없어 그대로 옮기면 판정 기록이 전부 실패.
  → **2단계 이관 제안**: 1단계 = 새 DB 서버에 `posture_app`도 함께 만들고 `DB_HOST`만 변경(코드 변경 없음), 2단계 = 회의 Q1·Q13 결정 후 V1.1로 코드 전환.
- 테스트 DB에 적용한 설정(bind-address, 방화벽, 계정, `max_connect_errors`, `innodb_flush_log_at_trx_commit`, 권장 InnoDB 값, 검증 절차)을
  **`테스트DB_설정_이관가이드.md`** 로 정리해 DB 담당에 전달.
- **D-19 신규(Blocked — DB 담당 설정 적용 대기)**, **D-20 신규(등록만)**: 시각 저장 기준(KST/UTC) 확인.

## 2026-10-06 갱신 메모 (T-11 완료 — 최대 동시 접속 12명)

- **T-11 → Done(DN-30)**: DB 연결 수정(JDBC `allowPublicKeyRetrieval`) 후 10~25명, 12~14명 측정.
  **현재 구성의 최대 동시 접속은 12명**(13명부터 lag 누적). 지속 처리 한계 약 105~110건/초, 병목은 DB 대기.
- PRD NFR-02·NFR-06·FR-BE-04·FR-OPS-08·위험 표를 실측에 맞게 갱신.
- 다음 후보: D-17(DB 설정)로 한계가 얼마나 오르는지 확인, D-18(DB 장애 시 판정 멈춤).

## 2026-10-06 갱신 메모 (T-11 정체 원인 확인, D-18 등록)

- T-11 1차 측정이 멈춘 원인은 **api-server → DB(192.168.0.42) 새 연결 생성 실패**로 확인. 용량 측정은 DB 연결 문제 해결 후 다시 한다.
- **D-18 신규 등록(미착수)**: DB 연결이 안 되면 실시간 판정 전체가 멈추는 구조 문제. 장애 격리 요구(NFR-06)와 어긋남.

## 2026-10-06 갱신 메모 (T-11 최대 동시 접속 측정)

- 사용자 지시로 **T-11** 신규 등록·착수. 현재 구성(파티션 3·컨슈머 3, DB 버퍼 풀 8MB)에서
  지연이 누적되지 않는 최대 동시 사용자 수를 찾는다. 측정 도구 패치 전달, 서버 실행 대기.

## 2026-10-05 갱신 메모 (우리 저장소 develop 병합, 회의 질문 목록)

- **우리 저장소(`dockerized-bigdata-env`) `develop`에 작업 단위별 PR #1~#5로 병합 완료**(사용자 진행):
  #1 D-13/D-14, #2 D-11, #3 D-15, #4 D-04, #5 D-16. 서버에 적용한 패치와 코드가 같음을 확인
  (추가분: `.gitignore`의 `mysql/*.csv`, `docs/CONVENTIONS.md`, `hadoop.env.example`). `main`은 아직 init 커밋.
- 앞으로 패치·작업은 `develop` 기준으로 하고, `docs/CONVENTIONS.md` 규칙(작업 브랜치 `<타입>/<범위>-<내용>`, develop으로 PR)을 따른다.
- **`팀회의_안건_질문목록.md`** 작성: 팀 저장소 분석·DB 스키마 매핑·D-03 안건·PRD 미결정 사항을 질문 28개로 통합
  (큰 방향 → 데이터 흐름 → 판정 정책 → DB → 통계 → 운영 순서, 결정 기록표·후속 작업표 포함).

## 2026-10-05 갱신 메모 (D-16 구현, 회의 자료)

- **D-16 → Done(DN-29)**: 종료 이벤트 목록을 최근 1000개로 제한, 서버에서 T-10 회귀 확인 완료.
- **회의 자료** `회의자료_DB스키마_매핑표.md`: 우리 `posture_app` ↔ 팀 `develop` V0.3 ↔ v4 테이블·컬럼 매핑.
  V0.3 채택을 제안(샘플마다 DB 쓰기가 없어지는 구조라 D-15/D-17 병목에도 유리), 대신 세션 시작 단계·이벤트 순번·알림 행·
  `last_seen_at`(→ Redis) 등 BE 변경이 필요. 판정 파라미터가 4곳에서 다름(V0.3 시드는 임계 0.5·재알림 30초).

## 2026-10-05 갱신 메모 (팀 저장소 분석)

- `팀저장소_분석_2026-10-05.md` 작성. 핵심: 팀 저장소의 서버 연동은 개인 브랜치 `jin_app`에 별도 백엔드(Esper·동기 REST·Kafka 없음)로
  구현돼 있어 우리 저장소·v4(DN-22)와 같은 기능을 두 갈래로 만들고 있음. DB 스키마도 세 갈래(우리 `posture_app` / `develop` V0.3 / `jin_app` V1).
- **D-14b → Blocked(팀 결정 대기)**: 기준 백엔드 트랙·전송 방식·입력 형식·CEP·T2·DB·인증·병합·런타임 버전 9개 안건.
- **D-03**: `develop` V0.3 `daily_stat`이 회의 안건 대부분에 답을 갖고 있음 → 회의 안건 문서에 반영.

## 2026-10-05 갱신 메모 (저장소 구조 확인)

- **저장소가 둘로 나뉘어 있음**: ① `dockerized-bigdata-env`(우리 저장소 — 인프라·api-server·inference-service,
  D-13~D-15/D-04/D-11 패치 대상) ② **팀 프로젝트 저장소**(FE 등, 별개). 아직 병합 전.
- **D-14b**: FE는 WebSocket 없이 이미 구현돼 팀 저장소에 있음 → FE 코드 분석부터.
- **D-09**: 팀 저장소로 병합된 뒤 CI/CD 경로·구조를 맞춰 수정.
- D-02·D-03·D-05는 회의·담당자 검토 필요(변동 없음).

## 2026-10-04 갱신 메모 (D-04 완료)

- **D-04 → Done(DN-28)**: 재생 도중 api-server를 재시작해도 진행 중이던 붕괴 이벤트가
  Redis에서 복원돼 재알림(alertCount=2)·종료(73.1s)까지 그대로 이어짐을 서버에서 확인.

## 2026-10-04 갱신 메모 (D-04 착수·구현)

- 사용자 지시("다른 ToDo 항목으로")에 따라 실행 가능한 최우선 항목인 **D-04**를 진행
  (D-02/D-03/D-05는 회의·담당자 대기, D-14b는 FE 경로 대기, D-17은 보류).
- 범위를 PRD FR-BE-04(상태머신 상태 Redis 저장)로 좁혀 구현 → Test(서버 검증 대기).

## 2026-10-04 갱신 메모 (D-15 완료, D-17 등록)

- **D-15 → Done(DN-27)**: 완료 기준(목표 동시 사용자에서 lag 누적 없음 + T-10 재현)을 충족.
  10Hz 전송으로 동시 10명을 약 10분 유지해도 lag 최대 38.
- **D-17 신규 등록(미착수)**: 동시 30명은 약 60초 뒤 처리율이 반 토막 — DB 서버의 InnoDB 버퍼 풀이
  8MB뿐이고(부하 중 디스크 읽기 255회/초), binlog도 커밋마다 fsync. 목표 이상의 여유를 원하면 DB 설정 조정.

## 2026-10-04 갱신 메모 (D-03 회의 안건 정리, D-15 후보 3 구현)

- **D-03 → Blocked(회의 대기)**: `period_stats` ↔ `mart_daily_posture` 매핑 회의
  안건 11개를 `회의안건_D-03_통계테이블_매핑.md`로 정리. 회의 결과가 나오면 착수.
- **D-15 → Test**: 후보 3 구현 패치 전달. 구현 중 **inference-service가
  `posture.inference`를 키 없이 발행**하고 있던 것을 발견 — 파티션만 늘렸다면
  같은 세션 메시지가 여러 파티션에 흩어져 판정 순서가 깨졌을 것. v4 규격대로
  키=userId로 수정. 검증 시 부하 테스트 CSV는 세션마다 다른 userId를 써야
  파티션이 고르게 쓰인다(지금까지는 전 세션이 P01 하나였음).
- **D-16 신규 등록(미착수)**: 엔진의 종료 이벤트 목록이 무한히 쌓이는 문제.

## 2026-10-04 갱신 메모 (D-11 완료)

D-11을 DN-26으로 완료 처리. DB 진단 결과 현 서버·구 VM 모두 연결 오류
누적 0 — 호스트 차단 재발 조짐 없음. `max_connect_errors`를 10000으로
영구 상향하고, HikariCP 수명 설정 명시 + 헬스체크를 liveness/readiness로
분리하는 패치를 서버 PC에 적용·검증했다(liveness/readiness UP, healthy).

## 2026-10-04 갱신 메모 (D-15 방향 확정, D-11 착수)

- **D-15**: DB 설정 조정(1차)으로 약 50% 개선까지 확인하고 일단 마무리. 남은
  구조적 병목은 **후보 (3) 파티션 + 컨슈머 동시성 증설로 추후 진행**하기로
  사용자가 결정 → Analysis에서 Development(착수 예정)로 이동.
- **D-11**: ToDo 다음 순서로 착수(Development → Analysis). DB 서버 진단 →
  `max_connect_errors` 상향, api-server HikariCP 명시 설정, 컨테이너
  헬스체크를 liveness로 분리하는 패치까지 한 번에 진행.

## 2026-10-04 갱신 메모 (D-15 1차 재측정 결과 — 처리율 약 50% 개선)

`innodb_flush_log_at_trx_commit=2` 적용 후 재측정 결과(30/50/70/100세션,
`--pace realtime`)를 분석했다. 각 단계 전송 완료 후 `api-server-cep` 잔여
lag를 드레인(소진)하는 데 걸린 시간:

| 세션 | 전송 소요 | 전송 종료 시 lag | 드레인 소요 | 드레인 처리율 |
|---|---|---|---|---|
| 30 | 64.97s | 1,563 | 28s | ≈55.8건/초 |
| 50 | 65.01s | 11,781 | 152s | ≈77.5건/초 |
| 70 | 65.12s | 22,375 | 297s | ≈75.3건/초 |
| 100 | 67.85s | 38,711 | 515s | ≈75.2건/초 |

DN-25 베이스라인(초당 ~49건, 메시지당 ~20ms)과 비교하면 50/70/100세션
구간에서 **초당 ~75건(메시지당 ~13ms)으로 약 50% 개선**됨. 30세션 구간은
표본(28초, lag 1,563건)이 작아 다소 낮게 나온 것으로 보임(초기 드레인
워밍업 영향 추정).

**10Hz 기준 실질 동시접속 한계는 기존 약 5명 → 약 7명으로 상향.**
단일 파티션/단일 컨슈머 스레드 구조는 그대로이므로, 이번 개선은 순수하게
메시지당 커밋 비용 감소(fsync 생략) 효과로 해석됨 — 구조적 병목(후보 1
throttle, 후보 3 파티션 증설)은 아직 그대로 남아있음.

**사용자 확인 완료**: 각 단계마다 재시작 후 컨슈머 lag가 0인 상태에서
실행한 클린 측정이 맞음. 위 결론(DB 설정 조정만으로 처리율 약 50%
개선, 동시접속 한계 약 5명→7명)을 **확정**한다. 단, 토픽 단일
파티션/단일 컨슈머 스레드 구조는 그대로라 구조적 한계는 남아있음.

D-15는 Analysis 상태 유지. 다음 단계(후보 1 throttle, 후보 3 파티션/
컨슈머 동시성 증설을 추가로 할지, 현재 ~7명 수준으로 충분한지)는
사용자 판단 대기.

## 2026-10-04 갱신 메모 (D-15 착수 — DB 설정 조정안으로 시작)

사용자가 DB 서버는 테스트 서버이고 설정 변경이 가능하다고 확인함에 따라,
D-15의 후보 조치 중 **(2) `innodb_flush_log_at_trx_commit=2` 조정안**부터
시작하기로 했다. 아직 결과는 나오지 않았고, 적용/재측정 절차는 다음과
같다.

1. 현재 값 확인: `SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';`
2. 동적 적용(재시작 불필요, 세션 재연결 시 반영): `SET GLOBAL innodb_flush_log_at_trx_commit=2;`
3. 영속 적용: `my.cnf`에 `innodb_flush_log_at_trx_commit=2` 추가 후 `systemctl restart mysql`
4. `api-server`/`inference-service` 재시작 → 컨슈머 lag 0 확인
5. 동일한 클린 방식(재시작 후 단일 단계)으로 50세션 `--pace realtime` 재측정
6. 드레인 구간 처리율을 기존 베이스라인(초당 ~49건)과 비교

D-15는 **ToDo → Analysis로 이동**, 결과 공유 시 효과를 기록하고 다음 단계
(후보 1: throttle, 후보 3: 파티션/컨슈머 동시성 증설 필요 여부)를 정한다.

## 2026-10-04 갱신 메모 (T-02/T-09 재측정 완료, DB 쓰기 병목 발견)

서버 PC에서 `replay_posture_pilot_csv.py --pace realtime`으로 동시 세션
30/50/70/100명 구간을 **매 단계마다 `api-server`/`inference-service`를
재시작하고 컨슈머 offset을 리셋한 뒤(깨끗한 상태에서)** 재측정했다.

**결론: REST 수집 자체는 문제없지만(실패 0, 지연시간 정상), `api-server-cep`
컨슈머가 메시지 1건당 약 20ms(동기 DB 커밋 1회)를 써서 — 동시 세션 수와
무관하게 처리율이 초당 약 50건으로 고정돼 있다.** 10Hz 전송 기준으로
환산하면 **현재 구조의 실질 동시접속 한계는 약 5명**이다. 원인은
`CepJdbcRepository`가 메시지마다 `@Transactional`/배치 없이 INSERT 1건씩
개별 커밋하는 구조 + `posture.inference` 토픽이 단일 파티션이라 처리
스레드가 1개뿐인 것의 조합. CPU는 1~7%로 낮아 GC/연산 병목이 아니라
I/O(커밋 대기) 병목임을 확인했다. HikariCP 풀(5)은 애초에 동시에 1개
커넥션만 쓰이므로 **풀 크기 자체는 부족하지 않다(T-09 결론)** — 다만 이건
병렬성을 전혀 안 쓰고 있어서이지, 풀이 넉넉해서가 아니다.

T-02/T-09는 이 결론으로 **Done 처리**(DN-25). 병목 수정은 새 항목
**D-15로 ToDo(백로그)에 등록만 해두고, 실제 착수는 보류** — 사용자 지시에
따라 "ToDo 리스트에 있는 항목만 진행" 원칙을 지키기 위함.

## 2026-10-03 갱신 메모 (D-13/D-14 전환 완료, T-10 재검증 통과)

서버 PC(192.168.0.104) 이전이 끝난 뒤, posture-cep 제거 + realtime-service
(api-server) 이식(D-13)과 docker-compose.yml v4 정렬(D-14)을 패치로
구현·적용했고, T-01 시나리오를 새 경로로 재생하는 T-10 재검증까지
통과했다.

- **D-13/D-14**: `api-server`에 `com.posture.api.posture.cep` 패키지로
  상태머신·DB 기록·세션 만료 로직을 포팅, `posture-cep` 서비스/컨테이너는
  `archive-posture-cep/`로 보관 후 compose에서 제거. Kafka 리스너에
  `EXTERNAL(9094, GPU PC 전용)` 추가, 내부 전용 포트(Kafka 9092/Redis
  6379/Spark 4040)는 `127.0.0.1` 바인딩, HDFS WebHDFS(9870/9864)는 GPU PC
  IP(192.168.0.108)로 제한, 전 서비스 로그 회전(`max-size 10m, max-file 3`)
  적용.
- **T-10**: `generate_collapse_test_csv.py`(850행, 정상5s+나쁜자세70s+회복10s)를
  새 경로(`api-server`→Kafka `posture.summary`→`inference-service`→Kafka
  `posture.inference`→`api-server`의 새 Java CEP 컨슈머)로 재생. 850/850
  성공, 로그에 `RE_ALERT(alertCount=2, 지속=63.0s)`→`EVENT_ENDED(지속시간=
  73.1s, alertCount=2)` 정확히 기록, `/cep/active`(종료 후 빈 목록)·
  `/cep/events/recent`(`recovered:true, durationSeconds:73.1`)·
  `collapse_events` DB 행(`duration_seconds=73.1, alert_count=2,
  recovered=1`) 세 곳 전부 일치, 에러 없음. **posture-cep 때 검증한
  판정 로직(DN-07/DN-19/DN-21)이 Java 포팅 후에도 동일하게 재현됨을
  확인.**
- 남은 건 Kafka 토픽을 v4 규격 5종 이름(`posture.keypoints` 등)으로
  실제로 리네이밍하는 것과 GPU PC `inference-service` 이전인데, 이건
  FE 키포인트 전송 경로(WebSocket)가 아직 없어서 당장 급하지 않음 —
  뒤로 미뤄도 되는 항목으로 재분류(아래 D-14b 참고).

## 2026-10-02 갱신 메모 (아키텍처 v4 전환 결정)

팀이 검토한 새 아키텍처 문서(`Kafka_메시지_규격_v1.md`,
`Posture_Architecture_v4.md`, `전체_설계안_v4.md`, 상세 비교는
`아키텍처_v4_검토의견_2026-10-02.md` 참고)를 반영하기로 하면서 아래 3가지를
결정했다.

1. **posture-cep 제거** — 상태머신 로직을 Spring `realtime-service`로 이식 (D-13)
2. **Kafka 토픽을 v4 규격(5종)으로 전환** (D-14)
3. **상태머신 파라미터(T1/T2/T3)는 지금 검증값(3초/3초/60초) 잠정 유지**, 팀 회의
   확정 시 수정
4. **동시성/처리량 수치(T-02/T-09)는 전환 후 새 경로 기준으로 재측정** — 기존
   776.7 req/sec 등의 수치는 REST 경로 기준이라 재사용 불가 (T-10 신설)

---

## Blocked (막힘)

| 작업 ID | 작업 내용 | 우선순위 | 비고 |
|---|---|---|---|
| D-19 | **새 DB 서버로 이관 (1단계: `posture_app` 병행)** | 2 | 테스트 DB → DB 담당 구축 DB. V1.1(`posture_service`)엔 현재 서버 테이블이 없어(`DB_V1.1_검토의견.md`) 1단계는 새 서버에 `posture_app`을 함께 만들고 `.env`의 `DB_HOST`만 바꿈. **DB 담당의 `테스트DB_설정_이관가이드.md` 적용(네트워크·계정·서버 변수) 대기**. 적용 후 BE가 가이드 6장 검증(readiness, T-10 재생, host_cache, 시간대). 2단계(V1.1 전환)는 회의 Q1·Q13 결정 후 별도 항목 |
| D-14b | Kafka 토픽 v4 리네이밍 + FE 연동 경로 | 4 | **→ D-21로 대체(2026-10-06)**. FE 연동 경로가 팀 `develop`의 `contracts/realtime/` 계약 초안으로 정의됨(토픽 `posture.*.v1`, 키 `session_id`, 게이트웨이 FE 담당). 기존 분석은 `팀저장소_분석_2026-10-05.md`. 남은 막힘은 Q1 결정·계약 확정 — D-21에서 추적 |
| D-03 | `period_stats`/`mart_daily_posture` 채우는 최소 집계 쿼리/배치 작성 | 3 | **팀 회의 대기** — 테이블 이름·집계 단위·`total_ms`/`bad_ms` 정의·작성 주체 등 11개 안건을 `회의안건_D-03_통계테이블_매핑.md`로 정리(2026-10-04). 결정되면 DDL 적용 후 착수. **회의 자료 `회의자료_DB스키마_매핑표.md` 작성(2026-10-05)** — V0.3 채택 시 BE 변경 8가지·결정 사항 8가지 정리. **2026-10-05: 팀 저장소 `develop`에 DB 담당 스키마 V0.3의 `daily_stat`이 이미 있어 안건 대부분에 답이 있음 — 회의 범위를 'V0.3 채택 여부'로 좁힘** |

---

## Analysis (분석 중)

| 작업 ID | 작업 내용 | 우선순위 | 비고 |
|---|---|---|---|
| D-25 | 팀 저장소 이전 + 전체 검토 | 3 | 사용자 계획(2026-10-06): **DB 이관·시험(D-19) 마무리 후** 우리 저장소 작업을 팀 저장소 `Jeon-Seho/sitting-posture-corrector`로 이전 — `develop` → `DevOps` 브랜치 → 작업별 브랜치. 이전 후 팀 저장소 전체(특히 `backend/cep`·`backend/api`·`compose.yaml`·`contracts/`)를 읽고 검토 → 검토의견 2.2(A/B) 확정 근거. D-09(CI/CD)·D-24와 연결. **순서 변경(10/06): D-19보다 먼저 진행.** 팀 저장소 `DevOps` 브랜치 생성 완료. 이전 방법(스냅샷 → `platform/`, CSV·가중치·워크플로 제외, MD 머리말·GP 카드) 사용자 확정 대기. **10/06: 프로젝트 문서 12개를 우리 저장소 `docs/`에 넣어 `main` 병합 후 함께 이동(사용자 결정)** |

---

## Development (개발 진행/예정)

| 작업 ID | 작업 내용 | 우선순위 | 비고 |
|---|---|---|---|
| D-02 | CSV 기반 연구 데이터 수집 체계 설계 | 2 | 저장 위치, 파일명 규칙, 참가자별/세션별 버전 관리, 팀원 간 공유 방식. **DB/ML 담당자 검토 사항으로 보류** |
| D-05 | Spark 배치 잡 — HDFS Parquet → `period_stats` 집계 | 3 | 세션별 통계(붕괴 횟수, 지속시간 분포) 계산 |
| D-07 | 인증/계정 기능 구현 | 4 | 현재 `userId`는 클라이언트가 보내는 자유 문자열, `accounts` 테이블은 placeholder |
| D-09 | CI/CD 파이프라인 재활성화 | 4 | `ci-api-server.yml`/`ci-inference-service.yml`/`cd-main.yml` 구현은 `dockerized-bigdata-env`(우리 저장소) 기준으로 완료, 보류 중. **2026-10-05 사용자 확인: 우리 저장소가 팀 프로젝트 저장소에 병합되면 그 구조에 맞게 수정 필요** — 병합 전까지 보류 |

---

## Test (테스트 필요/진행)

| 작업 ID | 작업 내용 | 우선순위 | 비고 |
|---|---|---|---|
| T-04 | 실제 참가자 데이터 수집 확대 및 라벨링 | 3 | 팀원 6명 → 외부 참가자, 2인 교차 라벨링 (CSV 기반으로 진행). DevOps/BE는 수집 파이프라인 지원 역할 — 라벨링 실행 자체는 담당자 영역 |

---

## ToDo (백로그, 미착수)

| 작업 ID | 작업 내용 | 우선순위 | 비고 |
|---|---|---|---|
| D-21 | Kafka 토픽·봉투·키를 실시간 계약 v1에 맞춤 | 2 | FE 연동안 J1 + 팀 `contracts/realtime/` 초안. 토픽 `posture.features.v1`·`posture.inference.v1`·`posture.episodes.v1`, 공통 봉투(`schema_version`·`message_id`·`session_id`·`user_id`·`produced_at`·`kind`·`body`), **키=`session_id`**(현재 inference 발행 키 userId(D-15)·Redis 키 userId(D-04)도 변경). D-14b 대체. 검토의견 `FE연동안_BE검토의견.md` 3장. **등록만, 미착수** — 계약 확정 후 |
| D-22 | 판정 결과 `posture.episodes.v1` 발행 + 추론 처리기 입력 v2/관측 v2 전환 | 2 | 연동안 H1 + 계약 추가 요구: `decision`(사건 v1+요약+`last_sequence`), `progress` 약 1초(이벤트 시각 기준), `event_id` 1부터, 사건을 progress보다 먼저. 추론: 입력 v2 수신, `observation`(`valid`(품질 0.65)·`collapse_probability`·`deviation_type`·`model_version`), `session_started/ended` 그대로 전달, 세션 종료 시 윈도우 정리(현재 세션 윈도우를 지우지 않아 메모리 증가). **판정 구현 A/B 결정(검토의견 2.2)·메시지 단위(2.1) 결정 전 착수 금지** |
| D-23 | 판정 정확도: 세션 정책·`sequence` 중복·제외 구간·명시적 종료 | 3 | 연동안 H2·H3·H4. 시작 메시지 `policy` 사용(환경변수는 기본값), `(session_id, sequence)` 중복 무시, `phase`(rest/away)·품질 `poor` → 제외 구간, `session_ended` 수신 시 즉시 최종 요약, 5분 만료는 `interrupted`. 저장은 판정이 아닌 저장 소비자가(검토의견 2.3). **2.2 결정 전 착수 금지** |
| D-24 | Kafka 외부 리스너 주소·포트 환경변수화 + 팀 `compose.yaml` 통합 준비 | 4 | 연동안 H5. 현재 `EXTERNAL://192.168.0.104:9094`, 포트 바인딩 `192.168.0.104:*` 고정. D-25(팀 저장소 이전)와 함께 진행 권장. **등록만, 미착수** |
| D-20 | 시각 저장 기준(KST/UTC) 확인 및 통일 | 3 | V1.1 검토 중 발견(미검증): JDBC `serverTimezone=Asia/Seoul` + `Timestamp.from(Instant)`라 DATETIME에 한국 시각이 저장될 가능성. 세션 만료 SQL은 `UTC_TIMESTAMP(3)`과 비교 → 사실이면 세션이 9시간 늦게 만료. 확인 쿼리: `SELECT session_id,last_seen_at,UTC_TIMESTAMP(3),NOW(3) FROM sessions ORDER BY last_seen_at DESC LIMIT 3` (D-19 검증 때 함께). 맞으면 서버를 UTC 기준으로 수정, V1.1에 "일시 컬럼 UTC 저장" 명시 요청(검토의견 #3). **등록만, 미착수** |
| D-18 | **DB 장애 시 실시간 판정 멈춤 해소** | 2 | T-11 중 발견: DB 연결을 못 얻으면 판정 컨슈머가 샘플마다 `sessions` upsert에서 5초씩 막혀(Hikari connection-timeout) 실시간 판정 전체가 멈추고, Kafka poll 제한 초과로 같은 묶음을 무한 재처리함. v4 장애 격리 요구(MySQL 장애 시 진행 중 세션 판정 유지, NFR-06)와 어긋남. 후보: DB 쓰기를 컨슈머 스레드에서 분리(비동기 큐/배치), DB 오류 시 일정 시간 쓰기 건너뛰기(D-04 Redis 저장소와 같은 방식), 판정 경로의 연결 대기 시간 단축, V0.3 전환 시 샘플별 쓰기 제거(회의 Q13·Q14). **등록만, 미착수** |
| D-17 | DB 서버(테스트 MySQL) 성능 설정 조정 + 부하 테스트 데이터 시각 보정 | 3 | D-15 지속 부하 중 발견: 동시 30명(초당 약 210건)은 처음 약 60초만 따라가고 이후 소비율이 약 245→118건/초로 떨어짐. `SHOW ENGINE INNODB STATUS`에서 **Buffer pool size 512페이지(=8MB)**, 부하 중 hit rate 858/1000, 디스크 읽기 255회/초 → 버퍼 풀이 작업 데이터를 못 담아 디스크를 계속 읽는 상태. 또 `log_bin=ON`, `sync_binlog=1`로 커밋마다 binlog fsync. 후보: `innodb_buffer_pool_size` 상향(예: 256MB, DB PC 메모리 확인 후), `sync_binlog=0`(테스트 서버 한정). 별도로 부하 CSV의 `capturedAt`이 2026-09-26(과거)이라 세션 만료 작업이 60초마다 테스트 세션 전체를 만료시킴 → `rebase_csv_to_now.py`로 시각 보정 후 측정 필요. **등록만, 미착수** |
| B-02 | Testcontainers 기반 통합 테스트 도입 | 5 | CI/CD 재활성화와 함께 진행 |

---

## Done (완료)

| 작업 ID | 작업 내용 | 우선순위 | 비고 |
|---|---|---|---|
| DN-01 | Kafka(KRaft, 단일 브로커) 컨슈머 그룹 소비 검증 | 3 | replication factor 이슈 해결 |
| DN-02 | api-server 수집 API 동기 Kafka 발행 + `/actuator/health` 검증 | 3 | |
| DN-03 | inference-service Kafka 컨슈머, 규칙 기반 분류, 테스트 LSTM 슬라이딩 윈도우 추론 검증 | 3 | 합성 데이터로 학습한 테스트 모델 |
| DN-04 | HDFS NameNode/DataNode 정상 동작, CLI read/write 검증 | 4 | |
| DN-05 | Spark `local[*]` HDFS Parquet 쓰기·읽기·파티셔닝 왕복 검증 | 4 | |
| DN-06 | posture-sink(Spark Structured Streaming) 10초 마이크로배치 HDFS 실시간 적재 검증 | 4 | 백로그+신규 이벤트 둘 다 확인 |
| DN-07 | posture-cep 상태 머신 — 지속조건(3초)·회복조건(3초)·재알림(60초) 검증 | 3 | 2026-09-30부로 최종 판정 구현으로 확정(DN-18). 2026-10-03 D-13으로 Java(api-server)로 포팅 완료, T-10에서 동일 동작 재확인(DN-23) |
| DN-08 | (폐기, 이력 참고) 연구DB CSV 소규모 적재 검증 — 15-2 | 5 | 543행, 0.491초, 평균 1107 rows/sec. 연구DB 자체는 2026-09-29 제거 결정, 2026-09-30 실제 제거 완료(DN-20 참고) |
| DN-09 | (폐기, 이력 참고) 연구DB 대용량 CSV 부하 테스트 — 15-3 | 5 | 271,500행, 382.610초, 평균 710 rows/sec (소규모 대비 약 36% 하락) |
| DN-10 | Kafka 파이프라인 재생(api-server→Kafka→inference) 처리량·지연시간 검증 — 15-4 | 2 | 세션50/27,150건: 730.4 req/sec, p99 209.2ms, 실패 0. REST 경로 기준 수치로, DN-25(T-02/T-09 재측정)의 비교군으로 사용됨 |
| DN-11 | 서비스DB(`posture_app`) 연결 확인 | 3 | `/actuator/health`에서 db·redis 모두 UP |
| DN-12 | 계획서 v2 "데이터베이스" 절 갱신 | 3 | 서비스DB/연구DB 2분리 폐기, 단일 서비스DB + 파일 기반 연구데이터로 변경 반영 |
| DN-13 | 계획서 v2 "빅데이터 플랫폼 구성" 절 쉬운 설명으로 재작성 | 4 | 대학생 2~3학년 수준으로 전문용어 풀어씀 (내용은 동일, 표현만 변경) |
| DN-14 | A-02: MySQL 호스트 차단 해제 (`mysqladmin flush-hosts`) | 2 | `docker logs api-server`에서 발견된 `Host '192.168.0.173' is blocked` 문제. 실행 완료, "Query OK" 확인. 단, 이 자체는 sessions 미기록의 근본 원인이 아니었음(DN-16 참고) |
| DN-15 | A-03: `SHOW TABLES` 스키마 불일치 원인 확인 | 2 | DB 미선택 상태로 조회해서 accounts/boards/users만 나왔던 것으로 확인. `USE posture_app;` 후 재조회 결과 `accounts`, `baseline_postures`, `collapse_events`, `period_stats`, `sessions` 전부 정상 존재. 테이블 구조는 문제없음 |
| DN-16 | A-01 최종 결론: `sessions` upsert는 버그가 아니라 미구현 기능으로 확정 | 1 | flush-hosts 이후에도 27만 건 재생(성공 271,500/실패 0) 후 sessions 여전히 0행 → 직접 INSERT 테스트 스크립트(`test_sessions_insert.py`)로 DB 쓰기 경로 자체는 정상임을 확인(+1행 성공) → api-server(Java) 소스 전체에 `Session` 클래스/`sessions` 참조 전혀 없음, 컨트롤러는 Kafka 발행만 함 → posture-cep(Python)의 `db.py`는 `collapse_events` upsert만 구현되어 있고 `sessions`는 다루지 않음 → inference-service도 관련 코드 없음. 결론: 프로젝트 전체에 sessions 테이블에 쓰는 코드가 애초에 없었다 |
| DN-17 | **D-12: `sessions` upsert 로직 구현 및 검증 완료** | 1 | posture-cep을 구현 위치로 선택(당시 기준, 2026-10-03 D-13으로 realtime-service(api-server)로 이식 완료). `app/db.py`에 `record_sample()` 추가 — `INSERT INTO sessions ... ON DUPLICATE KEY UPDATE last_seen_at=..., sample_count=sample_count+1`, capturedAt(Java Instant 나노초)을 `state_machine.parse_instant()`로 마이크로초까지 정규화. `app/consumer.py`의 `_handle_message()`에서 상태 전환 여부와 무관하게 매 샘플마다 호출하도록 연결. 단위테스트 6개 추가(전체 21개 통과). **VM 재검증 완료**: posture-cep 재빌드(`docker compose build --no-cache`) 후 543건 재생 → 로그에 `"MySQL 커넥션 풀 생성 완료"` 확인 → `sessions` 테이블에 실제로 행이 기록됨(사용자 확인 "성공함"). A-01/D-12 계열 전부 종결 |
| DN-18 | **D-06 취소: Esper 기반 CEP 미도입 결정** | 3 | 2026-09-30 결정. 8GB 서버에서 별도 JVM 서비스(posture-cep를 Esper로 전환 시 약 300~500MB)를 추가하면 메모리 여유가 없고, 판정 규칙(지속 3초·회복·재알림 60초)은 단순해 상태 머신으로 충분. 이미 VM 검증된 `state_machine.py`(DN-07)를 최종 구현으로 확정. 계획서 v2 "빅데이터 플랫폼 구성" 절·구현 메모·개정 이력(3차), `프로젝트_현황_및_다음단계` 문서(6차)에 반영 완료 |
| DN-19 | **D-10: 세션 만료·정리 로직 구현 및 VM 검증 완료** | 1 | 두 가지 독립적인 정리 경로를 추가: (1) `state_machine.py`의 `PostureCepEngine.expire_stale_sessions(now, timeout_seconds)` — 인메모리 세션 상태 정리, 진행 중이던 `collapse_events`는 `recovered=False`로 강제 종료; (2) `db.py`의 `expire_stale_sessions(timeout_seconds)` — `UPDATE sessions SET status='ENDED' WHERE status='ACTIVE' AND last_seen_at < (UTC_TIMESTAMP(3) - INTERVAL %s SECOND)`, posture-cep 재시작 후에도 독립적으로 동작. 새 `app/session_expiry.py`의 `SessionExpiryWorker`가 백그라운드 스레드(기본 60초 주기, 타임아웃 기본 300초)로 두 경로를 순차 실행하고, `app/main.py`에 수동 트리거용 `POST /cep/sessions/expire` 엔드포인트 추가. 단위테스트 7개 추가(전체 28개 통과). **VM 검증 완료(양방향 모두 확인)**: (a) 오래된 세션 → ENDED, (b) 신선한 세션 → ACTIVE 유지, (c) 그 신선한 세션도 5분 뒤 자연 만료 — 전체 사이클을 한 세션으로 실증. **2026-10-03 D-13으로 realtime-service(api-server)로 이식 완료** |
| DN-20 | **D-01: 연구DB(`posture_research`) 제거 완료** | 2 | 2026-09-29 팀 결정 실행. 확인 결과 `posture_research`는 별도 docker-compose 서비스/컨테이너가 아니라 서비스DB와 같은 MySQL 서버 위의 스키마였음 — 그래서 컨테이너 제거 단계는 해당 없음. (1) `.env`의 `RESEARCH_DB_*` 전부 삭제. (2) MySQL 서버에서 `DROP DATABASE posture_research;` 실행, `SHOW DATABASES;`로 목록에서 사라지고 `posture_app`만 남은 것 확인. (3) `mysql/load_posture_pilot_csv.py`, `mysql/test_db_connection.py` 등 `RESEARCH_DB_*` 참조 스크립트를 `mysql/archive/`로 이동(삭제 대신 보관 — CSV 재생/적재 로직 자체는 D-02 설계 시 참고 가치가 있어 보존). (4) `/actuator/health` 재확인 → `db`(posture_app) UP, `redis` UP 유지 확인. 연구DB 관련 작업 전부 종결 |
| DN-21 | **T-01: 나쁜 자세 구간 포함 CSV로 `collapse_events` 기록 검증 완료 (posture-cep, VM)** | 2 | 원본 `posture-pilot-P01.csv`(543행, 약 54초)는 전부 `rule_prediction=normal`이라 지속조건(3초)을 넘긴 사례가 없었음. `replay_posture_pilot_csv.py`의 매핑 로직(`rule_prediction="deviation"` → `ruleStatus=COLLAPSED`)을 확인한 뒤, `generate_collapse_test_csv.py`를 새로 작성 — 원본 앞부분(정상 5초)에 합성 구간(나쁜 자세 70초 + 회복 10초, 새 `session_id`/현재 시각 `started_at`)을 이어붙여 총 850행 CSV 생성. `--pace realtime`으로 재생(99.53초, 850건 성공/실패0) → posture-cep 로그에 `EVENT_STARTED`(지속조건 3.0s 충족) → `RE_ALERT`(alertCount=2, 지속 63.0s로 재알림 60s 조건 충족) → `EVENT_ENDED`(지속시간 73.1s, alertCount=2, 회복 확인) 순서로 정확히 기록됨. `/cep/events/recent`와 `collapse_events` DB 조회 모두 `recovered=1`, `alert_count=2`, `duration_seconds=73.1`로 일치. **2026-10-03 D-13 이후 동일 시나리오를 새 서버/Java 경로로 재검증 완료(DN-23/T-10)** |
| DN-22 | **아키텍처 v4 전환 검토 및 팀 결정 반영** | 1 | `Kafka_메시지_규격_v1.md`/`Posture_Architecture_v4.md`/`전체_설계안_v4.md` 검토(`아키텍처_v4_검토의견_2026-10-02.md` 작성) → posture-cep 제거 + realtime-service로 흡수(D-13), Kafka 토픽 v4 규격 전환(D-14), 상태머신 파라미터는 현재 검증값(3s/3s/60s) 잠정 유지, 동시성 수치는 전환 후 재측정(T-10)하기로 결정 |
| DN-23 | **D-13/D-14: posture-cep 제거 + api-server 이식, docker-compose v4 정렬 완료 (서버 PC 실측)** | 1 | GitHub 저장소(`dockerized-bigdata-env`) 클론 → `com.posture.api.posture.cep` 패키지(`PostureCepEngine`/`CepJdbcRepository`/`PostureInferenceConsumer`/`SessionExpiryScheduler`/`CepAdminController`)로 `state_machine.py`/`db.py`/`session_expiry.py`/`consumer.py`/`main.py` 로직 1:1 포팅, JUnit 테스트 12개로 원본 pytest 시나리오 전체 재현. `posture-cep`은 `archive-posture-cep/`로 보관 후 compose에서 제거, Kafka `EXTERNAL(9094)` 리스너 추가(GPU PC 192.168.0.108 전용), Kafka/Redis/Spark 내부 전용 포트는 `127.0.0.1` 바인딩, HDFS WebHDFS는 GPU PC IP로 제한, 전 서비스 로그 회전 설정 적용. 패치로 전달 → 사용자가 서버 PC(192.168.0.104)에 적용, `docker compose up -d --remove-orphans` 정상 기동(컨테이너 7개 모두 Healthy, `posture-cep` 없음), 신규 컨슈머 그룹 `api-server-cep`이 `posture.inference` 구독 성공, HikariCP MySQL 풀 정상 기동 확인 |
| DN-24 | **T-10: 전환 후(D-13/D-14) 새 경로로 T-01 시나리오 재검증 완료** | 2 | `generate_collapse_test_csv.py`로 만든 동일한 850행 합성 CSV(정상5s+나쁜자세70s+회복10s)를 `replay_posture_pilot_csv.py --pace fast`로 서버 PC의 `/api/v1/posture/summary`에 재생(850/850 성공, 116.7 req/sec는 참고용 수치일 뿐 T-02/T-09의 처리량 측정은 아님). api-server 로그에 `재알림(alertCount=2, 지속=63.0s)` → `붕괴 이벤트 종료(지속시간=73.1s, alertCount=2)` 정확히 기록, `GET /cep/active`(종료 후 빈 목록), `GET /cep/events/recent`(`recovered:true, durationSeconds:73.1, alertCount:2`), `collapse_events` DB 행(`duration_seconds=73.1, alert_count=2, recovered=1, ongoing=0`) 세 곳 모두 일치, 로그 전체에 예외 없음. posture-cep(Python, DN-21)에서 검증했던 결과와 동일 — **상태머신 로직이 Java 포팅 후에도 동일하게 동작함을 확인. D-13/D-14/T-10 전부 종결** |
| DN-25 | **T-02/T-09: 서버 PC 기준 처리량/DB풀 재측정 완료 — DB 쓰기 병목 발견** | 1 | 1차 시도(재시작 없이 연속 burst: 50/500/1000/2000세션)에서 `api-server-cep` lag가 17,025→862,886으로 누적 폭증 → 재시작 없이 연속 테스트한 것이 오염 요인일 수 있어 재설계. **2차(클린): 매 단계마다 `docker compose restart api-server inference-service` + 컨슈머 offset을 `--to-latest`로 리셋 후 `--pace realtime`으로 동시세션 30/50/70/100 측정.** 결과: REST 수집은 전 구간 실패 0, 지연시간 정상(HikariCP 고갈 없음 — PROCESSLIST 상 항상 활성 커넥션 1개뿐, **T-09 결론: 현재 풀 크기(5)는 부족하지 않음**, 단 이는 아래 병목으로 애초에 병렬 DB 접근이 거의 없기 때문). 반면 `api-server-cep` 쪽은 동시세션 수(30/50/70/100)와 무관하게 드레인 구간 처리율이 **초당 31~52건(메시지당 19~32ms)으로 거의 고정** — 세션 100명 테스트에서도 CPU는 7.4%로 낮아 GC/연산이 아니라 **I/O(동기 DB 커밋) 대기가 원인**임을 확인. `CepJdbcRepository`가 메시지마다 트랜잭션 묶음 없이 INSERT+커밋을 개별 수행하고, `posture.inference`가 단일 파티션이라 처리 스레드가 1개뿐인 구조적 한계로 결론. **T-02 결론: 10Hz 기준 현재 구조의 실질 동시접속 한계 ≈ 5명** (REST 단독 수용량 1000+ req/sec와는 완전히 별개 수치이며, 실시간 서비스 관점에서는 이 숫자가 진짜 한계). 기존 REST 경로 수치(DN-10, 776.7 req/sec)는 "수집 API가 받아줄 수 있는 양"일 뿐 "실시간으로 처리되는 양"이 아니었음을 명확히 함. 병목 해소 작업은 D-15로 별도 등록(미착수) |

| DN-26 | **D-11: `max_connect_errors` 상향 + HikariCP·헬스체크 설정 점검 완료** | 3 | **DB 진단(MySQL 8.0.25)**: `max_connect_errors=100`(기본), `wait_timeout=28800`, `max_connections=151`, `skip_name_resolve=OFF`, `Aborted_connects=20`, `Connection_errors_*` 전부 0. `performance_schema.host_cache`에서 현 서버(192.168.0.104)·구 VM(192.168.0.173) 모두 `SUM_CONNECT_ERRORS=0`, `COUNT_HOST_BLOCKED_ERRORS=0` — 오류는 과거에 몇 번 있었으나(구 VM 9/30~10/01, 현 서버 10/03 00:06 1회, D-13/D-14 배포 시점 추정) 이후 정상 연결로 카운터가 리셋돼 누적 없음. 즉 A-02(DN-14) 같은 차단이 지금 재발할 조짐은 없음. **조치**: ① `SET PERSIST max_connect_errors=10000`(재시작 후에도 유지) ② 패치 `D-11_hikari_healthcheck.patch` — HikariCP `pool-name=posture-app-pool`, `max-lifetime=30분`(< `wait_timeout` 8시간), `keepalive-time=5분`, `validation-timeout=3s` 명시, 헬스 그룹 분리(liveness=`livenessState` / readiness=`readinessState,db,redis`), compose 헬스체크를 `/actuator/health/liveness`로 변경. **검증(서버 PC)**: 로그에 `posture-app-pool - Start completed`, liveness `UP`, readiness(db·redis 포함) `UP`, 컨테이너 `healthy`. 차단 해제가 다시 필요하면 8.0.23+이므로 `FLUSH HOSTS` 대신 `TRUNCATE TABLE performance_schema.host_cache` 사용. (참고: `skip_name_resolve=ON`은 접속마다 역DNS 조회를 없애 주지만 MySQL 재시작과 계정 호스트 확인이 필요해 이번엔 적용 안 함 — 선택 사항) |

| DN-27 | **D-15: `api-server-cep` 처리량 병목 해소 완료 (DB 설정 + 파티션/컨슈머 동시성)** | 2 | ① 1차: DB `innodb_flush_log_at_trx_commit=2` → 드레인 처리율 ~49→~75건/초. ② 2차(후보 3): inference-service가 `posture.inference`를 **키=userId**로 발행(기존엔 키 없음 — 파티션 증설 시 순서 깨짐 위험), 파티션 1→3, `@KafkaListener` concurrency 3, HikariCP 풀 5→8, `KAFKA_NUM_PARTITIONS=3`. 검증: 스레드 3개가 파티션 0/1/2 하나씩 할당, **T-10 재현 통과**(재알림 63.0s → 종료 73.1s, alertCount=2). ③ **지속 부하**(10Hz 전송, 서로 다른 userId): **동시 10명 약 10분 7초 동안 lag 최대 38 — 목표(PRD NFR-02, 10명) 충족**(v4 전송 주기 사용자당 초당 약 2건 기준으로는 약 40명분 부하). 동시 30명은 처음 약 60초 따라가다 소비율이 약 245→118건/초로 떨어져 lag 누적 → 원인은 DB 서버 쪽(버퍼 풀 8MB 등)으로 D-17로 분리. 참고: 이전 '실질 한계 약 5명/7명'(DN-25)은 드레인 속도 기준이라 과소평가였음 |

| DN-28 | **D-04: 상태머신 상태 Redis 저장 완료 (PRD FR-BE-04)** | 3 | 판정 상태를 Redis `posture:state:{userId}`(Hash, TTL 1시간)에 상태가 바뀔 때만 저장하고, 재시작 등으로 메모리에 없는 세션은 첫 메시지에서 복원. 다른 세션·5분 넘은 상태는 버림, 정상 복귀 시 키 삭제, Redis 오류 시 10초간 건너뛰고 메모리로 판정 계속. 단위 테스트 7개 추가(기존 포함 18개 통과). **서버 검증(재시작 시점 스크립트로 고정)**: T-10 재생 20초 시점 `HGETALL` = state BAD·alertCount 1 → `docker compose restart api-server`(14:48:17 기동) → 2초 뒤 `저장소에서 상태 복원(state=BAD, alertCount=1)` → 재알림 alertCount=2(63.0s) → 종료 73.1s·alertCount=2. 재시작 없이 돌린 결과와 동일 — 재시작 중 수집 API 요청 일부 실패는 예상된 동작(api-server가 수집도 담당). 첫 시도는 재시작(14:31:14)이 이벤트 종료(14:30:28) 뒤에 일어나 복원이 검증되지 않았음. 범위 밖: `posture:latest`/`session:`/`ws:conn`/Pub/Sub(WebSocket 경로와 함께) |

| DN-29 | **D-16: 판정 엔진 종료 이벤트 목록 크기 제한 완료** | 4 | `PostureCepEngine.completedEvents`를 최근 N개(기본 1000, `CEP_RECENT_EVENTS_CAPACITY`) 고정 크기 큐로 변경 — 장시간 운영 시 메모리 증가 방지. 단위 테스트 1개 추가(기존 포함 19개 통과). **서버 회귀 확인(2026-10-05)**: 재빌드 후 T-10 CSV(`fed114e8…`) `--pace fast` 재생 850/850 성공, lag 0, 로그 확정 → 재알림(alertCount=2, 63.0s) → 종료(73.1s), `/cep/events/recent` = count 1, durationSeconds 73.1, alertCount 2, recovered true, ongoing false |

| DN-30 | **T-11: 서버 최대 동시 접속 측정 완료 — 12명** | 2 | 2026-10-06 사용자 지시로 신규 등록·착수. 기준: 동시 N명이 10Hz로 약 5~6분 이어서 보낼 때 ① HTTP 실패 0·p99 < 100ms ② 전송 중 lag이 계속 커지지 않음(최대 lag ≤ 5초분 = N×50건) ③ 전송 종료 후 15초 안에 lag 0 — 셋 다 만족하는 최대 N. 지금까지 근거: 10명 10분 통과, 30명은 약 60초 뒤 처리율 저하(DN-27). 도구 패치 `T-11_capacity_test_tooling.patch`(develop 기준): 재생 스크립트 `--live-timestamps`(전송 시각·실행별 새 세션 ID — 과거 시각 때문에 세션 만료 작업이 측정을 오염시키던 문제 제거), 단계 자동 실행 `mysql/run_capacity_stage.sh N [라운드]`(재시작 → lag 0 → 재생 → 드레인 측정 → 요약). 단계: 10(기준) → 15 → 20 → 25 → 실패 지점 사이 세분. DB 서버는 현재 설정(버퍼 풀 8MB) 그대로 — D-17 적용 시 재측정. **1차 실행(10/06 11:44, 동시 10명) 무효**: 전송 32,580건 성공(p99 16.8ms)이나 판정 컨슈머가 시작 44초 동안 16건만 처리(건당 약 2초)한 뒤 처리 위치가 멈춤 → lag 32,564에서 20분 넘게 그대로, 드레인 중 api-server CPU 0.1~0.5%(I/O 대기). 10/04 같은 10명 10분은 통과했으므로 용량이 아니라 환경·장애 문제로 판단(유력: 건당 처리 지연 → 500건 묶음이 `max.poll.interval`(5분) 초과 → 그룹에서 빠지고 같은 묶음 재처리 반복). 15·20·25명은 시작 전 남은 lag 때문에 진행 불가. **원인 확인(10/06 15:08)**: 측정 시작 직후(02:44:13Z)부터 HikariCP `Pool is empty, failed to create/setup connection` → 판정 컨슈머 3스레드가 매 메시지마다 `Failed to obtain JDBC Connection`(연결 대기 5초) → 500건 묶음이 poll 제한 시간 초과 → 그룹 이탈·재처리 반복. 즉 **용량이 아니라 DB 연결 실패**. 지금도 readiness `db: DOWN`. DB 설정(flush=2, max_connect_errors 10000)은 유지돼 있고 PROCESSLIST엔 서버 PC 연결 8개가 보여 '새 연결 생성이 간헐적으로 실패'하는 상태로 추정 — **근본 원인 확인(15:54)**: 연결 실패 187건 모두 `SQLNonTransientConnectionException: Public Key Retrieval is not allowed`. MySQL 8 기본 인증(caching_sha2_password)은 서버 인증 캐시가 비어 있으면(MySQL 재시작 직후 등) RSA 공개키로 비밀번호를 보내야 하는데, JDBC URL이 `useSSL=false`라 Connector/J가 공개키 요청을 막음 → 새 연결 전부 핸드셰이크 실패(`host_cache` COUNT_HANDSHAKE_ERRORS 2593, `Aborted_connects` 2594, 역DNS 오류 0). 다른 클라이언트가 로그인해 캐시가 채워지면 다시 붙는 간헐 현상. 9/29 호스트 차단(A-02/DN-14)도 같은 원인이었을 가능성이 큼(당시 `max_connect_errors` 100). 수정 패치 `fix-db-public-key-retrieval.patch`(JDBC URL에 `allowPublicKeyRetrieval=true`) 적용 완료. **2차 측정(10/06 16:07~16:40, DB 연결 수정 후, 6라운드·약 6분 지속)**: 10명 통과(최대 lag 24, 드레인 3초) / 15명 실패(최대 lag 5,345, 드레인 59초) / 20명 실패(16,591, 149초) / 25명 실패(31,123, 275초). HTTP는 전 단계 실패 0, p99 15~19ms. **지속 처리율이 부하와 무관하게 시작 약 2분 뒤 초당 약 107~116건으로 수렴**(처음 2분은 127~173건/초) → 실제 입력이 사용자당 초당 약 8.4건이라 **현재 구성의 최대 동시 접속 ≈ 13명(추정)**(10Hz 기준 약 11명). api-server CPU 평균 12~16%로 여전히 DB 대기(I/O) 병목, 시간이 지나며 처리율이 떨어지는 패턴은 DB 버퍼 풀(8MB) 문제(D-17)와 일치. 12·13명으로 경계 확정. **3차 측정(10/06 16:52~17:16, 경계 확정)**: 12명 통과(입력 101건/초, 최대 lag 131, 드레인 4초) / 13명 실패(110건/초, 최대 lag 1,517 > 기준 650, 전송 후반 lag +6.7건/초로 증가) / 14명 실패(118건/초, 최대 lag 3,283, 드레인 31초). **결론: 현재 구성 최대 동시 접속 = 12명**(재생 데이터 실측 사용자당 초당 약 8.4건 기준. 정확히 10Hz면 약 10명, v4 주기 사용자당 약 2건/초면 약 50명분). 지속 처리 한계 약 105~110건/초이며 시간이 갈수록 조금씩 떨어짐 → 6분보다 긴 운영에서는 12명도 경계선. 병목은 DB 대기(D-17/D-18) 단계 스크립트 보완 패치 `T-11b`(시작 전 readiness·lag 확인, 90초 무진척 시 즉시 중단, 단계별 api-server 경고 로그 저장) 전달 |
---

## 제외된 항목 (FE/ML 담당 — 이 문서 범위 아님)

DevOps/BE 담당자 기준 문서로 좁히면서 아래 항목을 이 문서에서
제거했다. 작업 자체가 없어진 게 아니라 **담당자가 다르다는 뜻**이며,
각자 별도로 관리한다.

| (구)작업 ID | 작업 내용 | 담당 |
|---|---|---|
| D-08 | 프론트엔드(React) 착수 | FE |
| T-05 | LSTM 실제 데이터 재학습 및 평가 (F1·AUROC) | ML |
| T-06 | ABA 파일럿 실험 실행 및 개선효과 검증 | ML/연구 |

---

## 사용 규칙 (이 문서를 계속 최신으로 유지하는 법)

1. 작업을 새로 시작하면 해당 항목을 알맞은 상태 섹션으로 옮긴다 (예: ToDo → Analysis → Development → Test → Done).
2. 작업 ID는 상태가 바뀌어도 유지한다 (예: `A-01`이 해결되면 `DN-14`로 새로 붙이지 않고, Done 섹션으로 옮기면서 원래 접두사를 유지하거나 이력용으로 그대로 남긴다 — 팀 편의에 따라 결정).
3. 새로운 이슈나 팀 결정이 생기면 이 문서에 먼저 반영한 뒤 `프로젝트_현황_및_다음단계` 문서와 계획서(v2)에도 필요한 부분만 반영한다.
4. 노션으로 옮길 때는 상태 섹션 제목을 노션 보드의 컬럼(ToDo/Analysis/Development/Test/Blocked/Done)으로, 표의 각 행을 카드로 옮기면 된다.
5. **작업은 이 문서의 ToDo/Analysis/Development/Test 섹션에 올라온 항목만 진행한다.** 테스트/분석 중 새로 발견된 이슈(예: D-15)는 바로 코드 작업으로 넘어가지 않고 먼저 이 문서에 항목으로 등록한 뒤, 사용자의 우선순위 지시를 받고 착수한다.
6. **이 문서는 DevOps/BE 담당 범위로 관리한다.** FE·ML 담당 항목은
   올리지 않거나(새로 생기는 경우), 이미 있던 것은 "제외된 항목" 표로
   옮겨 기록만 남긴다.
