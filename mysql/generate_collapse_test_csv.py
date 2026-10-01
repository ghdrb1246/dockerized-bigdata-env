#!/usr/bin/env python3
"""
posture-pilot-P01.csv를 기반으로, posture-cep 상태 머신의 지속조건(3초)·
재알림(60초)·회복조건(3초)을 전부 실제로 트리거할 수 있는 "나쁜 자세
구간 포함" 테스트 CSV를 만든다 (T-01 검증용).

배경:
  - replay_posture_pilot_csv.py는 CSV의 rule_prediction 컬럼이
    "deviation"이면 ruleStatus=COLLAPSED로, 그 외엔 NORMAL로 변환해서
    api-server에 보낸다.
  - posture-cep의 state_machine.py는 inferredStatus가 NORMAL/UNKNOWN이
    아니면 전부 "붕괴 후보"로 취급한다(지속 3초 이상이면 EVENT_STARTED).
  - 원본 P01 CSV는 543행(target_sample_hz=10 기준 약 54초)뿐이라, 재알림
    조건(60초)을 실제로 넘기기엔 길이가 모자란다.

이 스크립트가 하는 일:
  1. 원본 앞부분을 "정상 구간"(--warmup-sec, 기본 5초)으로 그대로 사용
  2. 그 뒤에 "나쁜 자세" 구간(--bad-sec, 기본 70초 = 지속조건 3초 +
     재알림 60초를 모두 넘기는 길이)을 합성해서 이어붙임
     (rule_prediction="deviation", delta_head_gap/offset/tilt와
     rule_score를 threshold=0.7보다 확실히 크게 설정)
  3. 다시 "회복 구간"(--cooldown-sec, 기본 10초 = 회복조건 3초를 넘기는
     길이)을 합성해서 마무리 (rule_prediction="normal")

합성 구간은 원본의 마지막 행을 템플릿으로 복사해서 elapsed_ms/
sample_index/video_time_ms만 이어서 증가시키고, 파이프라인이 실제로
쓰는 컬럼(rule_prediction/manual_label/delta_*/rule_score)만 바꾼다.
나머지 컬럼(landmarks_json 등)은 파이프라인이 쓰지 않으므로 원본 값을
그대로 복사한다 — CSV 파싱이 깨지지 않게 하는 용도일 뿐이다.

started_at도 지금 시각(UTC)으로 재설정하고 capture_id(session_id)도
새 UUID로 바꾼다 — D-10 세션 만료 로직 때문에 재생 직후 바로 "오래된
세션" 취급을 받거나, 기존에 이미 ENDED로 마킹된 세션과 섞이는 것을
피하기 위함.

사용법:
  python3 generate_collapse_test_csv.py \\
      --input posture-pilot-P01.csv \\
      --output posture-pilot-P01-collapse-test.csv
"""
import argparse
import csv
import uuid
from datetime import datetime, timezone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--warmup-sec", type=float, default=5.0)
    ap.add_argument("--bad-sec", type=float, default=70.0)
    ap.add_argument("--cooldown-sec", type=float, default=10.0)
    args = ap.parse_args()

    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not rows:
        raise SystemExit("입력 CSV에 데이터 행이 없습니다.")

    hz = float(rows[0].get("target_sample_hz") or 10)
    interval_ms = 1000.0 / hz
    template = dict(rows[-1])  # 합성 구간의 템플릿(landmarks_json 등 보존용)

    new_session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    started_at_str = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    out_rows = []

    def emit(row, elapsed_ms, sample_index, rule_prediction, manual_label,
             delta_head_gap, delta_offset, delta_tilt, rule_score):
        r = dict(row)
        r["capture_id"] = new_session_id
        r["started_at"] = started_at_str
        r["sample_index"] = str(sample_index)
        r["elapsed_ms"] = f"{elapsed_ms:.1f}"
        r["video_time_ms"] = f"{elapsed_ms:.1f}"
        r["gap_ms"] = f"{interval_ms:.1f}" if sample_index > 0 else ""
        r["rule_prediction"] = rule_prediction
        r["manual_label"] = manual_label
        r["delta_head_gap"] = f"{delta_head_gap:.6f}"
        r["delta_offset"] = f"{delta_offset:.6f}"
        r["delta_tilt"] = f"{delta_tilt:.6f}"
        r["rule_score"] = f"{rule_score:.6f}"
        out_rows.append(r)

    elapsed_ms = 0.0
    sample_index = 0

    # 1) 정상 구간 (원본 앞부분 재사용)
    n_warmup = max(int(args.warmup_sec * hz), 1)
    for row in rows[:n_warmup]:
        emit(row, elapsed_ms, sample_index,
             rule_prediction="normal", manual_label="upright",
             delta_head_gap=float(row.get("delta_head_gap") or 0),
             delta_offset=float(row.get("delta_offset") or 0),
             delta_tilt=float(row.get("delta_tilt") or 0),
             rule_score=float(row.get("rule_score") or 0.1))
        elapsed_ms += interval_ms
        sample_index += 1

    # 2) 나쁜 자세 구간 (합성) — 지속조건(3s) + 재알림(60s) 모두 커버
    n_bad = int(args.bad_sec * hz)
    for _ in range(n_bad):
        emit(template, elapsed_ms, sample_index,
             rule_prediction="deviation", manual_label="collapsed",
             delta_head_gap=0.18, delta_offset=0.15, delta_tilt=-0.12,
             rule_score=0.92)
        elapsed_ms += interval_ms
        sample_index += 1

    # 3) 회복 구간 (합성) — 회복조건(3s) 커버
    n_cool = int(args.cooldown_sec * hz)
    for _ in range(n_cool):
        emit(template, elapsed_ms, sample_index,
             rule_prediction="normal", manual_label="upright",
             delta_head_gap=0.02, delta_offset=0.01, delta_tilt=-0.01,
             rule_score=0.08)
        elapsed_ms += interval_ms
        sample_index += 1

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    total_sec = elapsed_ms / 1000.0
    print(f"완료: {args.output} ({len(out_rows)}행, 총 {total_sec:.1f}초)")
    print(f"  session_id(capture_id) = {new_session_id}")
    print(f"  started_at             = {started_at_str}")
    print(f"  구간: 정상 {n_warmup}행(~{args.warmup_sec:.0f}s) -> "
          f"나쁜자세 {n_bad}행(~{args.bad_sec:.0f}s) -> "
          f"회복 {n_cool}행(~{args.cooldown_sec:.0f}s)")
    print("예상 타임라인 (재생 시작 시각 기준):")
    print(f"  t=~{args.warmup_sec + 3:.0f}s   EVENT_STARTED (지속조건 3초 충족)")
    print(f"  t=~{args.warmup_sec + 63:.0f}s  RE_ALERT (최초 알림으로부터 60초 경과)")
    print(f"  t=~{args.warmup_sec + args.bad_sec + 3:.0f}s  EVENT_ENDED (회복조건 3초 충족)")


if __name__ == "__main__":
    main()