#!/usr/bin/env python3
"""
posture-pilot CSV(실제 파일럿 데이터 또는 generate_load_test_csv.py가
만든 대용량 CSV)를 실제 Kafka 파이프라인(api-server의 수집 API)으로
재생한다 — 합성(synthetic) LSTM 학습 데이터가 아니라 실제 MediaPipe
Pose 키포인트에서 뽑은 값으로 "클라이언트 → api-server → Kafka →
inference-service → posture-cep → (posture-sink → HDFS)" 전체
경로와 서비스DB(sessions/collapse_events) 기록까지 종단 검증하고,
동시에 "큰 데이터가 입력될 때 처리가 잘 되는지"(처리량/지연시간)를
측정하는 부하 테스트 스크립트다.

CSV 컬럼 -> PostureSummaryRequest 매핑 (api-server DTO 기준):
  sessionId      = capture_id
  userId         = participant_code
  capturedAt     = started_at + elapsed_ms (프레임별 실제 측정 시각)
  featureVector  = [delta_head_gap, delta_offset, delta_tilt]
                   (계획서 정의: "기준 자세 대비 정규화된 특징 벡터"와
                   정확히 대응하는 컬럼)
  deviationScore = rule_score (0~1 범위, DTO의 @DecimalMin/@Max와 일치)
  ruleStatus     = rule_prediction이 "deviation"이면 COLLAPSED, 아니면 NORMAL
  sampleRateHz   = target_sample_hz

세션(capture_id) 단위로 스레드를 하나씩 배정해 같은 세션 안에서는
프레임 순서를 지키면서(Kafka 파티션 키와 동일한 이유), 여러 세션을
동시에(--concurrency) 보내 동시 사용자 부하를 흉내낸다.

사용 예:
  # 스모크 테스트 (원본 파일럿 데이터 그대로, 빠르게)
  python3 replay_posture_pilot_csv.py --file posture-pilot-P01.csv \
      --api-url http://192.168.56.1:8080/api/v1/posture/summary --pace fast

  # (T-11) 최대 동시 접속 측정 — 실제 클라이언트처럼 '지금' 시각으로 보내고,
  # 실행마다 새 세션 ID를 쓴다(이전 실행의 세션·판정 상태와 섞이지 않게)
  python3 replay_posture_pilot_csv.py --file load-300.csv --pace realtime \
      --concurrency 20 --limit-sessions 120 --live-timestamps

  # 부하 테스트 (대용량 CSV, 세션 50개 동시)
  python3 replay_posture_pilot_csv.py --file posture-pilot-load-test.csv \
      --api-url http://192.168.56.1:8080/api/v1/posture/summary \
      --pace fast --concurrency 50
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import uuid
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import requests


def parse_started_at(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    return datetime.fromisoformat(v)


def to_request_payload(row: Dict[str, str]) -> Tuple[dict, float]:
    """CSV 한 행을 PostureSummaryRequest JSON으로 변환. elapsed_ms(ms)도 함께 반환(페이싱용)."""
    started_at = parse_started_at(row["started_at"])
    elapsed_ms = float(row["elapsed_ms"])
    captured_at = started_at + timedelta(milliseconds=elapsed_ms)

    rule_prediction = row.get("rule_prediction", "normal")
    rule_status = "COLLAPSED" if rule_prediction == "deviation" else "NORMAL"

    deviation_score = float(row["rule_score"]) if row.get("rule_score") else 0.0
    deviation_score = min(1.0, max(0.0, deviation_score))

    feature_vector = [
        float(row["delta_head_gap"]),
        float(row["delta_offset"]),
        float(row["delta_tilt"]),
    ]

    payload = {
        "sessionId": row["capture_id"],
        "userId": row["participant_code"],
        "capturedAt": captured_at.strftime("%Y-%m-%dT%H:%M:%S.") + f"{captured_at.microsecond // 1000:03d}Z",
        "featureVector": feature_vector,
        "deviationScore": round(deviation_score, 6),
        "ruleStatus": rule_status,
        "sampleRateHz": float(row["target_sample_hz"]) if row.get("target_sample_hz") else 10.0,
    }
    return payload, elapsed_ms


def group_by_session(rows: List[Dict[str, str]]) -> "OrderedDict[str, list]":
    sessions: "OrderedDict[str, list]" = OrderedDict()
    for row in rows:
        sessions.setdefault(row["capture_id"], []).append(row)
    return sessions


class SessionResult:
    __slots__ = ("session_id", "latencies_ms", "errors", "status_counts")

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.latencies_ms: List[float] = []
        self.errors: List[str] = []
        self.status_counts: Dict[int, int] = defaultdict(int)


def now_iso_millis() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def replay_session(
    session_id: str, rows: List[Dict[str, str]], api_url: str, pace: str, speed: float, timeout: float,
    live_session_id: str = None,
) -> SessionResult:
    result = SessionResult(session_id)
    session = requests.Session()

    prev_elapsed_ms = None
    for row in rows:
        payload, elapsed_ms = to_request_payload(row)
        if live_session_id is not None:
            # (T-11) --live-timestamps: 전송 순간의 시각과 이번 실행 전용 세션 ID 사용.
            # CSV의 과거 시각(capturedAt)을 쓰면 세션 만료 작업(60초 주기, 300초 타임아웃)이
            # 재생 중인 세션을 '오래된 세션'으로 계속 만료시켜 측정을 오염시킨다(D-17 참고).
            payload["sessionId"] = live_session_id

        if pace == "realtime" and prev_elapsed_ms is not None:
            gap_seconds = max(0.0, (elapsed_ms - prev_elapsed_ms) / 1000.0 / speed)
            if gap_seconds > 0:
                time.sleep(gap_seconds)
        prev_elapsed_ms = elapsed_ms

        if live_session_id is not None:
            payload["capturedAt"] = now_iso_millis()

        t0 = time.perf_counter()
        try:
            resp = session.post(api_url, json=payload, timeout=timeout)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            result.latencies_ms.append(latency_ms)
            result.status_counts[resp.status_code] += 1
            if resp.status_code != 202:
                result.errors.append(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            result.latencies_ms.append(latency_ms)
            result.errors.append(str(exc))

    session.close()
    return result


def percentile(values: List[float], p: float) -> float:
    if not values:
        return float("nan")
    return statistics.quantiles(values, n=100, method="inclusive")[int(p) - 1] if len(values) > 1 else values[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, nargs="+", help="posture-pilot CSV 경로 (여러 개 가능)")
    parser.add_argument("--api-url", default="http://localhost:8080/api/v1/posture/summary")
    parser.add_argument("--pace", choices=["fast", "realtime"], default="fast",
                         help="fast: 지연 없이 최대한 빠르게 전송(부하 테스트). realtime: elapsed_ms 간격을 재현(실측 타이밍 검증)")
    parser.add_argument("--speed", type=float, default=1.0, help="--pace realtime일 때 배속(2.0=2배 빠르게)")
    parser.add_argument("--concurrency", type=int, default=10, help="동시에 재생할 세션 수(스레드 수)")
    parser.add_argument("--timeout", type=float, default=10.0, help="요청당 타임아웃(초)")
    parser.add_argument("--limit-sessions", type=int, default=None, help="테스트용으로 앞에서 N세션만 재생")
    parser.add_argument("--live-timestamps", action="store_true",
                        help="capturedAt을 전송 시각(UTC)으로, sessionId를 실행마다 새 UUID로 바꿔 보낸다 "
                             "(실제 클라이언트 흉내. 최대 동시 접속 측정 T-11용)")
    args = parser.parse_args()

    all_rows: List[Dict[str, str]] = []
    for path in args.file:
        with open(path, encoding="utf-8-sig", newline="") as f:
            all_rows.extend(csv.DictReader(f))

    sessions = group_by_session(all_rows)
    session_items = list(sessions.items())
    if args.limit_sessions:
        session_items = session_items[: args.limit_sessions]

    total_requests = sum(len(rows) for _, rows in session_items)
    print(f"[재생 시작] 세션 {len(session_items)}개, 총 {total_requests}건, "
          f"동시성={args.concurrency}, pace={args.pace}, api={args.api_url}"
          + (", live-timestamps" if args.live_timestamps else ""))

    t0 = time.perf_counter()
    results: List[SessionResult] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(replay_session, sid, rows, args.api_url, args.pace, args.speed, args.timeout,
                        str(uuid.uuid4()) if args.live_timestamps else None)
            for sid, rows in session_items
        ]
        for fut in as_completed(futures):
            results.append(fut.result())
    elapsed = time.perf_counter() - t0

    all_latencies = [lat for r in results for lat in r.latencies_ms]
    all_status = defaultdict(int)
    error_samples = []
    for r in results:
        for code, count in r.status_counts.items():
            all_status[code] += count
        error_samples.extend(r.errors[:2])

    ok_count = all_status.get(202, 0)

    print(f"\n[결과] {elapsed:.2f}초 동안 {total_requests}건 전송 "
          f"({total_requests / elapsed:.1f} req/sec)")
    print(f"  성공(202): {ok_count} / 실패: {total_requests - ok_count}")
    print(f"  HTTP 상태 분포: {dict(all_status)}")
    if all_latencies:
        print(
            f"  지연시간(ms): avg={statistics.mean(all_latencies):.1f}  "
            f"p50={percentile(all_latencies, 50):.1f}  "
            f"p95={percentile(all_latencies, 95):.1f}  "
            f"p99={percentile(all_latencies, 99):.1f}  "
            f"max={max(all_latencies):.1f}"
        )
    if error_samples:
        print("\n  오류 샘플(최대 5개):")
        for msg in error_samples[:5]:
            print(f"    - {msg}")

    if total_requests - ok_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
