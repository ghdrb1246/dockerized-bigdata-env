"""
posture-sink가 특정 sessionId를 실제로 HDFS에 적재했는지 확인하는
1회성 배치 스크립트. pyspark REPL(대화형)은 docker exec -it의 TTY가
필요해 스크립트/파이프로는 못 돌리므로, spark-submit으로 비대화형
실행이 되게 분리했다.

사용법: spark 컨테이너 안에서
    spark-submit --master local[*] check_session.py <sessionId>
"""
import sys

from pyspark.sql import SparkSession

HDFS_URI = "hdfs://hdfs-namenode:9000"
STREAM_PATH = f"{HDFS_URI}/posture/features/stream"


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: check_session.py <sessionId>")
        sys.exit(2)

    session_id = sys.argv[1]

    spark = (
        SparkSession.builder.appName("posture-sink-check")
        .config("spark.hadoop.fs.defaultFS", HDFS_URI)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    df = spark.read.parquet(STREAM_PATH)
    matched = df.filter(df.sessionId == session_id)
    count = matched.count()

    print(f"[CHECK] sessionId={session_id!r} 로 {count}건 발견")
    if count > 0:
        matched.show(truncate=False)
        print("[RESULT] posture-sink가 이 세션을 HDFS에 적재했습니다 (성공)")
    else:
        print("[RESULT] 아직 적재되지 않았습니다 — 10~20초 더 기다렸다가 다시 실행해보세요")

    spark.stop()


if __name__ == "__main__":
    main()
