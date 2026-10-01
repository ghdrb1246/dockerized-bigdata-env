#!/usr/bin/env python3
"""
posture-pilot 원본 CSV(예: posture-pilot-P01.csv) 한 세션을 템플릿으로
삼아, 서로 다른 capture_id/participant_code/started_at을 가진 N개의
세션으로 복제한 대용량 CSV를 만든다.

목적: "큰 데이터가 입력될 때 처리가 잘 되는가"를 테스트하려면 실제
분포에 가까운 대량의 행이 필요한데, 지금 단계에서는 파일럿 참가자가
1명(P01, 543행)뿐이다. 이 스크립트로 수백~수천 세션 규모(수십만 행)
CSV를 만들어 load_posture_pilot_csv.py(MySQL 대량 삽입)와
replay_posture_pilot_csv.py(Kafka 파이프라인 재생) 양쪽의 부하
테스트 입력으로 쓴다.

완전히 똑같은 행을 N배 복사하면 의미가 없으므로, 기본적으로 특징
컬럼(head_gap/lateral_offset/shoulder_tilt/delta_*/rule_score)에
작은 가우시안 잡음을 더해 세션마다 조금씩 다른 시계열을 만든다
(--jitter 0으로 끄면 순수 복제).

사용 예:
  python3 generate_load_test_csv.py \
      --template posture-pilot-P01.csv \
      --sessions 500 \
      --participants P01 P02 P03 \
      --out posture-pilot-load-test.csv
  # 543행 x 500세션 = 271,500행
"""
from __future__ import annotations

import argparse
import csv
import random
import uuid
from datetime import datetime, timedelta

NUMERIC_JITTER_COLUMNS = [
    "head_gap", "lateral_offset", "shoulder_tilt",
    "delta_head_gap", "delta_offset", "delta_tilt", "rule_score",
]


def read_template(path: str):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    return fieldnames, rows


def parse_started_at(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    return datetime.fromisoformat(v)


def format_started_at(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def generate(fieldnames, template_rows, n_sessions, participants, jitter, seed, session_gap_seconds):
    rng = random.Random(seed)
    base_start = parse_started_at(template_rows[0]["started_at"])

    for i in range(n_sessions):
        capture_id = str(uuid.uuid4())
        participant_code = participants[i % len(participants)]
        session_start = base_start + timedelta(seconds=i * session_gap_seconds)

        for row in template_rows:
            new_row = dict(row)
            new_row["capture_id"] = capture_id
            new_row["participant_code"] = participant_code
            new_row["started_at"] = format_started_at(session_start)

            if jitter > 0:
                for col in NUMERIC_JITTER_COLUMNS:
                    raw = new_row.get(col)
                    if raw:
                        try:
                            new_row[col] = repr(float(raw) + rng.uniform(-jitter, jitter))
                        except ValueError:
                            pass
            yield new_row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, help="원본 posture-pilot CSV 경로")
    parser.add_argument("--out", required=True, help="생성할 대용량 CSV 경로")
    parser.add_argument("--sessions", type=int, default=200, help="복제할 세션 수")
    parser.add_argument("--participants", nargs="+", default=None,
                         help="순환 배정할 participant_code 목록 (기본: 템플릿의 원래 값 1개만 사용)")
    parser.add_argument("--jitter", type=float, default=0.01,
                         help="특징 컬럼에 더할 균등분포 잡음 폭(±). 0이면 순수 복제")
    parser.add_argument("--session-gap-seconds", type=float, default=120.0,
                         help="세션 간 started_at 간격(초) — capturedAt 기반 로직에 영향 없이 세션을 구분만 함")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    fieldnames, template_rows = read_template(args.template)
    participants = args.participants or sorted({r["participant_code"] for r in template_rows})

    total_rows = args.sessions * len(template_rows)
    print(f"[생성] 템플릿 {len(template_rows)}행 x 세션 {args.sessions}개 = {total_rows}행 "
          f"(참가자 순환: {participants})")

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        count = 0
        for row in generate(
            fieldnames, template_rows, args.sessions, participants,
            args.jitter, args.seed, args.session_gap_seconds,
        ):
            writer.writerow(row)
            count += 1

    print(f"[완료] {args.out} ({count}행)")


if __name__ == "__main__":
    main()
