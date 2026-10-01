#!/usr/bin/env python3
"""
posture-pilot-P01.csv (또는 유사한 재생용 CSV)의 타임스탬프를 "지금"
기준으로 밀어서 새 CSV를 만든다. D-10(세션 만료) 검증용 —
"신선한(방금 발생한) 세션이 즉시 ACTIVE로 남아있는지"를 확인하려면
capturedAt이 실제로 최근이어야 하는데, 고정 pilot CSV는 항상
2026-09-26 시각을 담고 있어서 재생해도 항상 "오래된 세션"이 된다.

동작:
  1. CSV에서 타임스탬프로 보이는 컬럼(capturedAt, serverReceivedAt 등
     ISO-8601로 파싱되는 컬럼)을 자동 탐지한다.
  2. 그 컬럼들 중 최댓값을 찾아, "지금(UTC)"과의 차이(delta)를 구한다.
  3. 모든 타임스탬프 컬럼의 모든 값에 delta를 더해 "마지막 행이
     지금 막 도착한 것"처럼 만든다. 행간 간격(pace)은 그대로 보존된다.
  4. session_id 컬럼이 있으면 새 UUID로 치환한다 — 기존에 이미
     ENDED로 마킹된 옛 session_id를 재사용하면, sessions 테이블의
     upsert가 status는 갱신하지 않으므로(last_seen_at/sample_count만
     갱신) status가 영원히 ENDED로 남는 문제를 피하기 위함.

사용법:
  python3 rebase_csv_to_now.py posture-pilot-P01.csv posture-pilot-P01-now.csv
"""
import csv
import sys
import uuid
from datetime import datetime, timezone

TIMESTAMP_COLUMN_HINTS = ("capturedat", "serverreceivedat", "startedat", "endedat", "timestamp")


def try_parse_iso(value: str):
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    # Java Instant.toString() 스타일: 나노초(최대 9자리) + 'Z'
    if v.endswith("Z"):
        v_body = v[:-1]
        if "." in v_body:
            head, frac = v_body.split(".", 1)
            frac = (frac + "000000")[:6]  # 마이크로초로 절단/패딩
            v_body = f"{head}.{frac}"
        v = v_body + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def format_like_original(dt: datetime, original: str) -> str:
    """원본 문자열이 'Z'로 끝났으면 'Z'로, 나노초 자릿수도 최대한 맞춰서 되돌린다."""
    had_z = original.strip().endswith("Z")
    dt_utc = dt.astimezone(timezone.utc)
    # 원본의 소수점 자릿수를 보존 (없으면 초 단위까지만)
    if "." in original:
        frac_len = len(original.strip().rstrip("Z").split(".", 1)[1])
    else:
        frac_len = 0

    base = dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
    if frac_len > 0:
        micros = f"{dt_utc.microsecond:06d}"
        frac = (micros + "0" * 9)[:frac_len]  # 마이크로초를 요청 자릿수만큼 패딩
        base = f"{base}.{frac}"
    return base + ("Z" if had_z else "+00:00")


def main():
    if len(sys.argv) != 3:
        print(f"사용법: {sys.argv[0]} <입력.csv> <출력.csv>", file=sys.stderr)
        sys.exit(1)

    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames:
        print("CSV에 헤더가 없습니다.", file=sys.stderr)
        sys.exit(1)

    ts_columns = [c for c in fieldnames if c.lower() in TIMESTAMP_COLUMN_HINTS]
    if not ts_columns:
        # 힌트에 없으면, 첫 행에서 실제로 ISO 파싱되는 컬럼을 탐지
        for c in fieldnames:
            if rows and try_parse_iso(rows[0].get(c, "")) is not None:
                ts_columns.append(c)

    if not ts_columns:
        print("타임스탬프 컬럼을 찾지 못했습니다. TIMESTAMP_COLUMN_HINTS를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    print(f"타임스탬프 컬럼: {ts_columns}")

    # 전체 타임스탬프 중 최댓값을 찾는다
    max_dt = None
    for row in rows:
        for c in ts_columns:
            dt = try_parse_iso(row.get(c, ""))
            if dt is not None and (max_dt is None or dt > max_dt):
                max_dt = dt

    if max_dt is None:
        print("타임스탬프를 하나도 파싱하지 못했습니다.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    delta = now - max_dt
    print(f"원본 최댓값={max_dt.isoformat()}, 지금={now.isoformat()}, delta={delta}")

    session_id_columns = [c for c in fieldnames if c.lower() == "sessionid"]
    new_session_id_map = {}

    for row in rows:
        for c in ts_columns:
            original = row.get(c, "")
            dt = try_parse_iso(original)
            if dt is not None:
                row[c] = format_like_original(dt + delta, original)
        for c in session_id_columns:
            old_id = row.get(c, "")
            if old_id not in new_session_id_map:
                new_session_id_map[old_id] = str(uuid.uuid4())
            row[c] = new_session_id_map[old_id]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"완료: {out_path} ({len(rows)}행)")
    if new_session_id_map:
        print(f"session_id 치환: {new_session_id_map}")


if __name__ == "__main__":
    main()