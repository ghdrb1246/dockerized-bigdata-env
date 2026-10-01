#!/usr/bin/env python3
"""
DB 생성 권한이 없어도(스키마를 만들 필요 없이) MySQL에 실제로 접속되는지
만 빠르게 확인하는 스크립트. DB 구축은 담당자가 진행하고, 우리 쪽은
"연결이 되는가"만 반복해서 확인하면 되는 상황을 위한 것 — 접속이 되면
서버 버전과 (해당 데이터베이스가 이미 만들어져 있다면) 그 안의 테이블
목록까지 보여준다. 스키마 자체를 만들거나 바꾸는 동작은 전혀 하지
않는다(READ ONLY 성격의 점검 스크립트).

사용 예:
  # 서비스DB 연결 확인 (담당자가 posture_app을 만들어줬는지)
  python3 test_db_connection.py --host 192.168.0.42 --user posture_app \
      --password changeme --database posture_app

  # DB가 아직 없어도 서버 자체 접속만 확인 (database 생략)
  python3 test_db_connection.py --host 192.168.0.42 --user root --password ****

  # .env 파일을 그대로 읽어서 확인 (서비스DB/연구DB 둘 다)
  python3 test_db_connection.py --env-file ../.env
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import mysql.connector
    from mysql.connector import errorcode
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


def check(label: str, host: str, port: int, user: str, password: str,
          database: Optional[str], timeout: float) -> bool:
    print(f"\n=== {label}: {user}@{host}:{port}/{database or '(DB 미지정, 서버 접속만 확인)'} ===")
    t0 = time.perf_counter()
    try:
        conn = mysql.connector.connect(
            host=host, port=port, user=user, password=password,
            database=database,
            # mysql-connector-python의 C 확장(_mysql_connector)은
            # connect_timeout을 C int로 받는다 — float(예: 5.0)를 그대로
            # 넘기면 "TypeError: argument 4 must be int, not float"가
            # 난다. --timeout을 float로 받는 이유(초 단위를 자연스럽게
            # 적게 하려고)는 유지하고, 여기서만 정수로 잘라 넘긴다.
            connection_timeout=max(1, int(round(timeout))),
        )
    except mysql.connector.Error as exc:
        elapsed = time.perf_counter() - t0
        print(f"  [실패] {elapsed:.2f}초 만에 접속 실패: {exc}")
        if exc.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("  -> 계정/비밀번호 또는 접속 허용 호스트('user'@'%')를 담당자에게 재확인하세요.")
        elif exc.errno == errorcode.ER_BAD_DB_ERROR:
            print(f"  -> '{database}' 데이터베이스가 아직 만들어지지 않았습니다(담당자 작업 대기 중).")
        elif "timed out" in str(exc).lower() or getattr(exc, "errno", None) in (2003, None):
            print("  -> 네트워크로 아예 도달하지 못했습니다. VM 네트워크 어댑터가 Bridged인지,")
            print("     외부 PC의 방화벽/3306 포트, bind-address 설정을 확인하세요")
            print("     (mysql/README_MySQL_구축_가이드.md 3절).")
        return False

    elapsed = time.perf_counter() - t0
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    version = cursor.fetchone()[0]
    print(f"  [성공] {elapsed:.2f}초, MySQL {version}")

    if database:
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        if tables:
            print(f"  테이블 {len(tables)}개: {', '.join(tables)}")
        else:
            print("  테이블 없음 — 담당자가 아직 posture_app_schema.sql / posture_research_schema.sql을 실행하지 않았을 수 있습니다.")

    cursor.close()
    conn.close()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default=None, help="생략하면 서버 접속 자체만 확인")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--env-file", help=".env 파일을 읽어 서비스DB(DB_*)/연구DB(RESEARCH_DB_*) 둘 다 확인")
    args = parser.parse_args()

    ok = True
    if args.env_file:
        env = load_env_file(args.env_file)
        ok &= check(
            "서비스DB (posture_app)",
            env.get("DB_HOST", ""), int(env.get("DB_PORT", 3306)),
            env.get("DB_USER", "posture_app"), env.get("DB_PASSWORD", ""),
            env.get("DB_NAME", "posture_app"), args.timeout,
        )
        ok &= check(
            "연구DB (posture_research)",
            env.get("RESEARCH_DB_HOST", env.get("DB_HOST", "")),
            int(env.get("RESEARCH_DB_PORT", 3306)),
            env.get("RESEARCH_DB_USER", "posture_research"),
            env.get("RESEARCH_DB_PASSWORD", ""),
            env.get("RESEARCH_DB_NAME", "posture_research"), args.timeout,
        )
    else:
        if not args.host or not args.user:
            parser.error("--env-file을 안 쓸 경우 --host/--user는 필수입니다.")
        ok = check("접속 확인", args.host, args.port, args.user, args.password,
                    args.database, args.timeout)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
