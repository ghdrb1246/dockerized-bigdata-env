#!/usr/bin/env python3
"""
posture-pilot 수집 CSV(예: posture-pilot-P01.csv)를 연구DB
(posture_research)에 적재한다.

용도 두 가지:
  1) 실제 파일럿 데이터를 연구DB에 넣어 "데이터가 실제로 저장되는가"를
     확인한다 (--file 하나).
  2) generate_load_test_csv.py로 만든 대용량 CSV를 넣어 "큰 데이터가
     입력될 때 처리가 잘 되는가"(배치 삽입 처리량, 초당 행 수)를
     측정한다 (--file 큰 CSV, --batch-size로 배치 크기 조절).

한 capture_id(수집 세션)는 CSV 안에서 여러 행(프레임)으로 나온다.
참가자(participants) → 수집 세션(collection_sessions) → 표본
(posture_samples) 순서로 적재하며, posture_samples는 대량 삽입
성능이 중요하므로 executemany()로 배치 처리한다.

접속 정보(호스트/계정/비밀번호)는 커맨드라인 인자로 직접 줄 수도
있고, `.env` 파일의 RESEARCH_DB_* 값을 그대로 읽어 쓸 수도 있다
(--host/--user 등을 매번 타이핑하지 않아도 되게, test_db_connection.py
와 같은 방식). 둘 다 있으면 커맨드라인 인자가 우선한다.

사용 예:
  # .env(RESEARCH_DB_HOST/PORT/NAME/USER/PASSWORD)에서 접속 정보를 읽음
  python3 load_posture_pilot_csv.py --file posture-pilot-P01.csv --env-file ../.env

  # 인자로 직접 지정 (.env보다 우선)
  python3 load_posture_pilot_csv.py \
      --file posture-pilot-P01.csv \
      --host 192.168.0.42 --user posture_research --password changeme

의존성: pip install mysql-connector-python  (환경에 따라 --break-system-packages 필요할 수 있음)
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import mysql.connector
except ImportError:
    print(
        "mysql-connector-python이 필요합니다: "
        "pip install --break-system-packages mysql-connector-python",
        file=sys.stderr,
    )
    raise


SESSION_COLUMNS = [
    "capture_id", "participant_code", "schema_version", "started_at",
    "pose_model", "feature_version", "calibration_seconds", "target_sample_hz",
    "task_id", "activity", "requested_head_direction", "requested_posture",
    "requested_presence", "repetition", "planned_seconds", "camera_view",
    "camera_height", "distance_cm", "desk_layout", "stop_reason",
    "calibration_id", "width", "height", "delegate", "review_status",
    "pose_training_eligible",
]

SAMPLE_COLUMNS = [
    "capture_id", "sample_index", "elapsed_ms", "video_time_ms", "gap_ms",
    "segment_id", "manual_label", "label_source", "measurement_quality",
    "head_gap", "lateral_offset", "shoulder_tilt", "visibility",
    "baseline_head_gap", "baseline_offset", "baseline_tilt",
    "delta_head_gap", "delta_offset", "delta_tilt", "rule_score",
    "rule_prediction", "threshold", "hold_seconds", "realert_seconds",
    "recover_seconds", "inference_ms", "pose_detected", "landmark_count",
    "landmarks_json", "world_landmarks_json",
]

_BOOL_COLUMNS = {"pose_training_eligible", "pose_detected"}
_INT_COLUMNS = {"repetition", "width", "height", "landmark_count", "sample_index"}
_FLOAT_COLUMNS = {
    "calibration_seconds", "target_sample_hz", "planned_seconds", "distance_cm",
    "elapsed_ms", "video_time_ms", "gap_ms", "head_gap", "lateral_offset",
    "shoulder_tilt", "visibility", "baseline_head_gap", "baseline_offset",
    "baseline_tilt", "delta_head_gap", "delta_offset", "delta_tilt",
    "rule_score", "threshold", "hold_seconds", "realert_seconds",
    "recover_seconds", "inference_ms",
}


def _coerce(column: str, raw: Optional[str]) -> Any:
    if raw is None or raw == "":
        return None
    if column in _BOOL_COLUMNS:
        return 1 if raw.strip() == "1" else 0
    if column in _INT_COLUMNS:
        return int(float(raw))
    if column in _FLOAT_COLUMNS:
        return float(raw)
    if column == "started_at":
        return _to_mysql_datetime(raw)
    return raw


def _to_mysql_datetime(iso_value: str) -> str:
    value = iso_value.replace("T", " ")
    if value.endswith("Z"):
        value = value[:-1]
    return value


def load_env_file(path: str) -> Dict[str, str]:
    """.env를 간단히 파싱한다(python-dotenv 없이 KEY=VALUE 줄만 읽음).

    test_db_connection.py의 load_env_file()과 동일한 방식 — 이 프로젝트는
    스크립트를 서로 독립적으로 실행 가능하게 유지하는 편이라(공용 모듈
    없이 각자 self-contained) 의도적으로 중복시켰다.
    """
    values: Dict[str, str] = {}
    env_path = Path(path)
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def read_rows(path: str) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_sessions(rows: Iterable[Dict[str, str]]) -> "OrderedDict[str, tuple]":
    """capture_id별 첫 행을 세션 메타데이터로 쓰고, sample_count는 나중에 채운다."""
    sessions: "OrderedDict[str, tuple]" = OrderedDict()
    counts: Dict[str, int] = {}
    for row in rows:
        capture_id = row["capture_id"]
        counts[capture_id] = counts.get(capture_id, 0) + 1
        if capture_id in sessions:
            continue
        values = tuple(_coerce(col, row.get(col)) for col in SESSION_COLUMNS)
        sessions[capture_id] = values
    # sample_count를 마지막 컬럼으로 덧붙인다
    return OrderedDict(
        (cid, values + (counts[cid],)) for cid, values in sessions.items()
    )


def build_participants(rows: Iterable[Dict[str, str]]) -> List[Tuple[str]]:
    codes = OrderedDict()
    for row in rows:
        codes.setdefault(row["participant_code"], None)
    return [(code,) for code in codes]


def build_samples(rows: Iterable[Dict[str, str]]) -> List[tuple]:
    return [tuple(_coerce(col, row.get(col)) for col in SAMPLE_COLUMNS) for row in rows]


def load(conn, rows: List[Dict[str, str]], batch_size: int) -> Dict[str, float]:
    cursor = conn.cursor()
    timings: Dict[str, float] = {}

    t0 = time.perf_counter()
    participants = build_participants(rows)
    cursor.executemany(
        "INSERT IGNORE INTO participants (participant_code) VALUES (%s)", participants
    )
    conn.commit()
    timings["participants_sec"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    sessions = build_sessions(rows)
    session_cols = SESSION_COLUMNS + ["sample_count"]
    placeholders = ", ".join(["%s"] * len(session_cols))
    update_clause = ", ".join(
        f"{c} = VALUES({c})" for c in session_cols if c != "capture_id"
    )
    sql = (
        f"INSERT INTO collection_sessions ({', '.join(session_cols)}) "
        f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_clause}"
    )
    cursor.executemany(sql, list(sessions.values()))
    conn.commit()
    timings["sessions_sec"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    samples = build_samples(rows)
    placeholders = ", ".join(["%s"] * len(SAMPLE_COLUMNS))
    sql = f"INSERT INTO posture_samples ({', '.join(SAMPLE_COLUMNS)}) VALUES ({placeholders})"
    for start in range(0, len(samples), batch_size):
        batch = samples[start:start + batch_size]
        try:
            cursor.executemany(sql, batch)
            conn.commit()
        except mysql.connector.errors.OperationalError as exc:
            if exc.errno == 1153:  # ER_NET_PACKET_TOO_LARGE
                raise SystemExit(
                    "\n[오류] MySQL 서버의 max_allowed_packet보다 배치 크기가 큽니다.\n"
                    f"  현재 --batch-size={batch_size}. posture_samples는 한 행에 "
                    "landmarks_json/world_landmarks_json(약 7~8KB)이 들어있어 "
                    "일반 테이블보다 행 하나가 훨씬 무겁습니다.\n"
                    "  해결 방법 (둘 중 하나, 또는 둘 다):\n"
                    "    1) --batch-size를 줄여서 재실행 (예: --batch-size 100)\n"
                    "    2) DB 담당자에게 max_allowed_packet을 늘려달라고 요청:\n"
                    "         - 즉시 적용(재시작 불필요): MySQL 콘솔에서\n"
                    "           SET GLOBAL max_allowed_packet = 67108864;  -- 64MB\n"
                    "         - 영구 적용: my.cnf의 [mysqld]에 max_allowed_packet=64M 추가 후 재시작\n"
                ) from exc
            raise
    timings["samples_sec"] = time.perf_counter() - t0
    timings["samples_count"] = len(samples)

    cursor.close()
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, nargs="+", help="posture-pilot CSV 경로 (여러 개 가능)")
    parser.add_argument("--env-file", default="../.env",
                         help="RESEARCH_DB_HOST/PORT/NAME/USER/PASSWORD를 읽어올 .env 경로 "
                              "(파일이 없으면 조용히 무시 — 기본값 ../.env)")
    parser.add_argument("--host", default=None, help="생략하면 --env-file의 RESEARCH_DB_HOST 사용")
    parser.add_argument("--port", type=int, default=None, help="생략하면 --env-file의 RESEARCH_DB_PORT 사용")
    parser.add_argument("--database", default=None, help="생략하면 --env-file의 RESEARCH_DB_NAME 사용")
    parser.add_argument("--user", default=None, help="생략하면 --env-file의 RESEARCH_DB_USER 사용")
    parser.add_argument("--password", default=None, help="생략하면 --env-file의 RESEARCH_DB_PASSWORD 사용")
    parser.add_argument("--batch-size", type=int, default=200,
                         help="posture_samples 배치 삽입 크기 (기본 200). 한 행에 landmarks_json/"
                              "world_landmarks_json(약 7~8KB)이 들어있어, 큰 값을 주면 MySQL "
                              "서버의 max_allowed_packet을 넘겨 'Got a packet bigger than "
                              "max_allowed_packet' 오류가 날 수 있다 — 서버 설정을 올렸다면 "
                              "더 크게 줘도 된다(처리량은 올라감).")
    args = parser.parse_args()

    env = load_env_file(args.env_file)
    # 우선순위: 커맨드라인 인자 > .env > 하드코딩된 최후 기본값.
    host = args.host or env.get("RESEARCH_DB_HOST") or "127.0.0.1"
    port = args.port or int(env.get("RESEARCH_DB_PORT", 3306))
    database = args.database or env.get("RESEARCH_DB_NAME") or "posture_research"
    user = args.user or env.get("RESEARCH_DB_USER") or "posture_research"
    password = args.password if args.password is not None else env.get("RESEARCH_DB_PASSWORD", "changeme")

    conn = mysql.connector.connect(host=host, port=port, database=database, user=user, password=password)
    print(f"[연결] {user}@{host}:{port}/{database}"
          f"{' (.env: ' + args.env_file + ')' if env else ''}")

    total_rows = 0
    grand_t0 = time.perf_counter()
    for path in args.file:
        print(f"\n=== {path} 읽는 중 ===")
        rows = read_rows(path)
        print(f"  {len(rows)}행 파싱 완료 (participant={ {r['participant_code'] for r in rows} }, "
              f"capture={ {r['capture_id'] for r in rows} })")
        timings = load(conn, rows, args.batch_size)
        total_rows += len(rows)
        rate = timings["samples_count"] / timings["samples_sec"] if timings["samples_sec"] > 0 else float("inf")
        print(
            f"  participants: {timings['participants_sec']:.3f}s | "
            f"sessions: {timings['sessions_sec']:.3f}s | "
            f"samples: {timings['samples_count']}행 / {timings['samples_sec']:.3f}s "
            f"({rate:.0f} rows/sec)"
        )

    elapsed = time.perf_counter() - grand_t0
    overall_rate = total_rows / elapsed if elapsed > 0 else float("inf")
    print(f"\n[결과] 총 {total_rows}행, {elapsed:.3f}초, 평균 {overall_rate:.0f} rows/sec")

    conn.close()


if __name__ == "__main__":
    main()
