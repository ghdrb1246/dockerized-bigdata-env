#!/usr/bin/env bash
# =====================================================================
# (T-11) 최대 동시 접속 측정 — 한 단계(동시 사용자 N명)를 깨끗한 상태에서
# 실행하고 결과를 capacity-results/<시각>-n<N>/ 에 남긴다.
#
# 순서: api-server·inference-service 재시작 → 컨슈머 재참여·lag 0 대기
#       → lag/자원 기록 시작 → N명 동시 재생(실시간 속도, 지금 시각)
#       → 전송 종료 후 lag 0까지 걸린 시간(드레인) 측정 → 요약 출력
#
# 사용법 (저장소 루트 또는 아무 위치에서):
#   mysql/run_capacity_stage.sh <동시 사용자 수> [라운드 수=6] [CSV=mysql/load-300.csv]
#
# 한 라운드 = 세션 1개 길이(약 54초). 라운드 6이면 N명이 약 5~6분 동안 이어서 접속한다
# (재생 세션 수 = N × 라운드). CSV에는 세션이 N × 라운드 개 이상 있어야 한다.
# =====================================================================
set -eu   # pipefail은 쓰지 않음 — kafka CLI가 순간 실패해도 awk가 0을 내고 계속 진행

N=${1:?"동시 사용자 수를 지정하세요. 예: mysql/run_capacity_stage.sh 15"}
ROUNDS=${2:-6}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
CSV=${3:-mysql/load-300.csv}
LIMIT=$((N * ROUNDS))
OUT="capacity-results/$(date +%Y%m%d-%H%M%S)-n${N}"
mkdir -p "$OUT"

KG="docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group"

# describe 출력에서 posture.* 토픽 행만 골라 합계를 낸다 (컬럼: GROUP TOPIC PARTITION CURRENT LOG-END LAG CONSUMER-ID ...)
sum_lag()      { awk '$2 ~ /^posture\./ && $6 ~ /^[0-9]+$/ {l += $6} END {print l + 0}'; }
sum_consumed() { awk '$2 ~ /^posture\./ && $4 ~ /^[0-9]+$/ {c += $4} END {print c + 0}'; }
count_members(){ awk '$2 ~ /^posture\./ && $7 != "-" {m++} END {print m + 0}'; }
describe()     { $KG "$1" 2>/dev/null || true; }
lag_of()       { describe "$1" | sum_lag; }
members_of()   { describe "$1" | count_members; }

wait_until() {  # wait_until <제한초> <설명> <조건 명령...>
  local limit=$1 desc=$2; shift 2
  local start=$SECONDS
  until "$@"; do
    if (( SECONDS - start > limit )); then echo "[중단] ${desc} — ${limit}초 안에 충족되지 않음"; exit 1; fi
    sleep 3
  done
}
cep_ready() { [ "$(members_of api-server-cep)" -ge 3 ] && [ "$(members_of inference-service)" -ge 1 ]; }
lag_zero()  { [ "$(lag_of api-server-cep)" -eq 0 ] && [ "$(lag_of inference-service)" -eq 0 ]; }

[ -f "$CSV" ] || { echo "[중단] CSV 없음: $CSV (generate_load_test_csv.py로 먼저 생성)"; exit 1; }

echo "== T-11 단계: 동시 ${N}명 × ${ROUNDS}라운드 (세션 ${LIMIT}개), 결과 → ${OUT}"

echo "[1/5] api-server · inference-service 재시작"
docker compose restart api-server inference-service >/dev/null
wait_until 180 "컨슈머 재참여" cep_ready
echo "[2/5] lag 0 대기"
wait_until 300 "시작 전 lag 0" lag_zero

echo "[3/5] 기록 시작 (lag: 5초 간격 / 자원: 15초 간격)"
(
  echo "time,elapsed_s,cep_consumed,cep_lag,inf_lag"
  t0=$SECONDS
  while true; do
    ts=$(date +%T); el=$((SECONDS - t0))
    cep=$(describe api-server-cep)
    echo "${ts},${el},$(echo "$cep" | sum_consumed),$(echo "$cep" | sum_lag),$(lag_of inference-service)"
    sleep 2   # kafka CLI 호출 2회(약 3초) + 2초 ≈ 5초 간격. elapsed_s 컬럼이 실제 간격
  done
) > "$OUT/lag.csv" &
LAG_PID=$!
(
  while true; do
    echo "--- $(date +%T)"
    docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' api-server inference-service kafka redis || true
    sleep 15
  done
) > "$OUT/stats.log" 2>&1 &
STATS_PID=$!
trap 'kill $LAG_PID $STATS_PID 2>/dev/null || true' EXIT

echo "[4/5] 재생 (동시 ${N}명, 실시간 속도, 전송 시각 사용)"
SEND_START=$SECONDS
set +e
python3 mysql/replay_posture_pilot_csv.py --file "$CSV" --pace realtime \
  --concurrency "$N" --limit-sessions "$LIMIT" --live-timestamps > "$OUT/replay.log" 2>&1
REPLAY_RC=$?
set -e
SEND_SECONDS=$((SECONDS - SEND_START))
LAG_AT_END_CEP=$(lag_of api-server-cep)
LAG_AT_END_INF=$(lag_of inference-service)

echo "[5/5] 드레인 측정 (lag 0까지, 최대 15분)"
DRAIN_START=$SECONDS
until lag_zero; do
  if (( SECONDS - DRAIN_START > 900 )); then echo "  드레인 15분 초과 — 중단"; break; fi
  sleep 3
done
DRAIN_SECONDS=$((SECONDS - DRAIN_START))
sleep 5   # 마지막 lag 샘플 기록
kill $LAG_PID $STATS_PID 2>/dev/null || true
trap - EXIT

MAX_LAG=$(awk -F, 'NR > 1 && $4 > m {m = $4} END {print m + 0}' "$OUT/lag.csv")
{
  echo "동시 사용자: ${N}명 / 라운드: ${ROUNDS} / 세션: ${LIMIT}개 / 입력: 약 $((N * 10))건/초 (10Hz)"
  echo "전송 시간: ${SEND_SECONDS}초 (재생 종료 코드 ${REPLAY_RC})"
  grep -E "^\[결과\]|성공\(202\)|지연시간" "$OUT/replay.log" | sed 's/^ *//'
  echo "전송 종료 시 lag: api-server-cep=${LAG_AT_END_CEP}, inference-service=${LAG_AT_END_INF}"
  echo "전송 중 최대 lag(api-server-cep): ${MAX_LAG}"
  echo "드레인(lag 0까지): ${DRAIN_SECONDS}초"
} | tee "$OUT/summary.txt"
echo "== 완료: ${OUT} (summary.txt, lag.csv, stats.log, replay.log)"
