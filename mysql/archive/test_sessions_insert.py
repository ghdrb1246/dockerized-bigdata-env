#!/usr/bin/env python3
"""
posture_app.sessions 테이블에 "정말 아무거나" 하나라도 직접 넣히는지만
확인하는 최소 테스트 스크립트.

목적: api-server를 거치지 않고, 이 스크립트가 DB에 직접 접속해서
INSERT ... ON DUPLICATE KEY UPDATE 한 줄을 성공시키면 -> DB 쓰기 경로
자체(계정 권한, 네트워크, 테이블 스키마)는 문제가 없다는 뜻이다.
그런데도 api-server가 27만 건을 202로 성공 처리하면서 sessions에는
아무것도 안 남았다면, 결론은 하나로 좁혀진다: "api-server 코드가
sessions upsert를 아예 호출하지 않고 있다"(A-04).

이 스크립트는:
  1. 시작 전 sessions 행 개수를 센다.
  2. 테스트 session_id 하나를 INSERT ON DUPLICATE KEY UPDATE로 넣는다.
  3. 그 행을 SELECT로 다시 읽어 실제로 저장됐는지 확인한다.
  4. 끝난 뒤 sessions 행 개수를 다시 세서 +1(또는 갱신) 됐는지 보여준다.
  5. --cleanup을 주면 테스트 행을 지운다 (기본은 남겨둠 -> 나중에 직접
     확인하거나, 그대로 두고 재검증할 때 last_seen_at 갱신을 봐도 됨).

사용 예:
  # .env 파일 그대로 사용 (서비스DB: DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME)
  python3 test_sessions_insert.py --env-file ../.env

  # 직접 접속 정보 지정
  python3 test_sessions_insert.py --host 192.168.0.42 --user posture_app \
      --password changeme --database posture_app

  # 테스트 후 넣은 행 삭제까지
  python3 test_sessions_insert.py --env-file ../.env --cleanup
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import mysql.connector
except ImportError:
    print(
        "mysql-connector-python이 필요합니다: "
        "pip install --break-system-packages mysql-connector-python",
        file=sys.stderr,
    )
    raise


def load_env_file(path: str) -> dict:
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="posture_app")
    parser.add_argument("--env-file", help=".env 파일에서 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 읽기")
    parser.add_argument("--cleanup", action="store_true", help="테스트 후 넣은 행을 삭제")
    args = parser.parse_args()

    if args.env_file:
        env = load_env_file(args.env_file)
        host = env.get("DB_HOST", "")
        port = int(env.get("DB_PORT", 3306))
        user = env.get("DB_USER", "posture_app")
        password = env.get("DB_PASSWORD", "")
        database = env.get("DB_NAME", "posture_app")
    else:
        if not args.host or not args.user:
            parser.error("--env-file을 안 쓸 경우 --host/--user는 필수입니다.")
        host, port, user, password, database = args.host, args.port, args.user, args.password, args.database

    print(f"=== 접속: {user}@{host}:{port}/{database} ===")
    conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=database,
        connection_timeout=5,
    )
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM sessions")
    before_count = cursor.fetchone()[0]
    print(f"[시작 전] sessions 행 개수: {before_count}")

    test_session_id = f"debug-test-{uuid.uuid4().hex[:12]}"
    test_user_id = "debug-user"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    print(f"\n[삽입 시도] session_id={test_session_id}")
    try:
        cursor.execute(
            """
            INSERT INTO sessions (session_id, user_id, started_at, last_seen_at, sample_count, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                last_seen_at = VALUES(last_seen_at),
                sample_count = sample_count + 1
            """,
            (test_session_id, test_user_id, now, now, 1, "ACTIVE"),
        )
        conn.commit()
        print(f"  [성공] INSERT 실행됨, affected_rows={cursor.rowcount}")
    except mysql.connector.Error as exc:
        print(f"  [실패] INSERT 자체가 에러남: {exc}")
        print("  -> 이 경우가 진짜 중요하다: DB 쓰기 권한/스키마 문제가 아직 남아있다는 뜻.")
        cursor.close()
        conn.close()
        sys.exit(1)

    cursor.execute(
        "SELECT session_id, user_id, started_at, last_seen_at, sample_count, status "
        "FROM sessions WHERE session_id = %s",
        (test_session_id,),
    )
    row = cursor.fetchone()
    if row:
        print(f"  [확인] 방금 넣은 행 조회 성공: {row}")
    else:
        print("  [경고] INSERT는 에러 없이 끝났는데 SELECT로 안 보임 (매우 이례적 - 트랜잭션/격리수준 문제 의심)")

    cursor.execute("SELECT COUNT(*) FROM sessions")
    after_count = cursor.fetchone()[0]
    print(f"\n[종료 후] sessions 행 개수: {after_count} (변화: {after_count - before_count:+d})")

    if row and after_count > before_count:
        print(
            "\n=== 결론 ===\n"
            "이 스크립트로는 DB에 직접 넣혔다. 즉 sessions 테이블 쓰기 경로\n"
            "(계정 권한/네트워크/스키마)는 정상이다.\n"
            "그런데도 api-server가 수만 건을 202로 처리하면서 sessions에\n"
            "아무것도 안 남는다면, 결론은 'api-server 코드가 sessions upsert를\n"
            "아예 호출하지 않는다'(A-04)로 좁혀진다. api-server 소스에서\n"
            "sessions 저장 관련 리포지토리/서비스 코드를 다시 찾아봐야 한다."
        )

    if args.cleanup:
        cursor.execute("DELETE FROM sessions WHERE session_id = %s", (test_session_id,))
        conn.commit()
        print(f"\n[정리] 테스트 행 삭제 완료 (session_id={test_session_id})")
    else:
        print(f"\n[참고] 테스트 행을 남겨뒀다 (session_id={test_session_id}). 지우려면 --cleanup 옵션을 쓰거나 직접 DELETE.")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
