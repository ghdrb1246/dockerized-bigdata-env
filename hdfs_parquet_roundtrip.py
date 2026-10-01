"""
HDFS/Spark 기능 검증용 테스트 스크립트.

목적: 계획서의 "빅데이터 플랫폼 구성" 중 posture-sink(Spark Structured
Streaming)가 궁극적으로 하게 될 일 — 정규화 특징값을 HDFS에 Parquet
형태로, 이벤트 시각 기준으로 파티셔닝하여 적재 — 을 아주 단순화한
배치 버전으로 재현해서, "컨테이너가 떠 있다"가 아니라 "Spark가 실제로
HDFS에 쓰고 다시 읽을 수 있다"를 확인한다.

posture-sink 자체(Structured Streaming, 5~10초 마이크로배치)는 아직
구현 대상이 아니다 — 이 스크립트는 그 전 단계인 "Spark ↔ HDFS 배관이
뚫려 있는가"만 검증하는 1회성 배치 테스트다.

실행 방법은 이 파일과 같은 디렉토리의 README 참고.
"""
import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

HDFS_URI = "hdfs://hdfs-namenode:9000"
OUTPUT_PATH = f"{HDFS_URI}/posture/features/roundtrip-test"


def main() -> None:
    spark = (
        SparkSession.builder.appName("posture-hdfs-roundtrip-test")
        .config("spark.hadoop.fs.defaultFS", HDFS_URI)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    now = datetime.datetime.utcnow()
    event_date = now.strftime("%Y-%m-%d")

    # posture.summary 이벤트를 흉내낸 예시 레코드 3건
    rows = [
        ("session-hdfs-test", "user-1", now.isoformat(), 0.12, "NORMAL"),
        ("session-hdfs-test", "user-1", now.isoformat(), 0.35, "WARNING"),
        ("session-hdfs-test", "user-1", now.isoformat(), 0.61, "BAD"),
    ]
    columns = ["sessionId", "userId", "capturedAt", "deviationScore", "status"]

    df = spark.createDataFrame(rows, columns).withColumn("eventDate", F.lit(event_date))

    print(f"[STEP 1] {OUTPUT_PATH} 에 Parquet로 쓰기 시작 ({df.count()}건)")
    df.write.mode("overwrite").partitionBy("eventDate").parquet(OUTPUT_PATH)
    print("[WRITE OK] HDFS에 Parquet 파일 쓰기 완료")

    print(f"[STEP 2] {OUTPUT_PATH} 에서 다시 읽기")
    read_df = spark.read.parquet(OUTPUT_PATH)
    count = read_df.count()
    print(f"[READ OK] {count}건 읽음 (쓴 건수와 같아야 정상)")
    read_df.orderBy("deviationScore").show(truncate=False)

    if count != len(rows):
        raise SystemExit(
            f"[FAIL] 쓴 건수({len(rows)})와 읽은 건수({count})가 다르다 — HDFS 적재에 문제가 있다"
        )

    print("[RESULT] HDFS <-> Spark 왕복 테스트 성공")
    spark.stop()


if __name__ == "__main__":
    main()
