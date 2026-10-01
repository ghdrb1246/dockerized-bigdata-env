#!/usr/bin/env bash
# posture_sink_stream.py를 spark 컨테이너에 복사하고, 컨테이너 안의
# Spark/Scala 버전을 자동 감지해 그에 맞는 spark-sql-kafka 커넥터
# 좌표로 백그라운드 실행한다.
#
# 사용법: docker-compose.yml 이 있는 디렉토리에서
#   ./run_posture_sink.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VERSION_OUTPUT=$(docker exec spark /opt/spark/bin/spark-submit --version 2>&1 || true)
echo "---- spark-submit --version 출력 ----"
echo "$VERSION_OUTPUT"
echo "-------------------------------------"

SPARK_VERSION=$(echo "$VERSION_OUTPUT" | grep -oE 'version [0-9]+\.[0-9]+\.[0-9]+' | head -1 | awk '{print $2}')
SCALA_MAJOR_MINOR=$(echo "$VERSION_OUTPUT" | grep -oE 'Scala version [0-9]+\.[0-9]+' | head -1 | awk '{print $3}' | cut -d. -f1,2)

if [ -z "$SPARK_VERSION" ] || [ -z "$SCALA_MAJOR_MINOR" ]; then
  echo "[FAIL] 위 출력에서 Spark/Scala 버전을 자동으로 읽지 못했습니다."
  echo "       위 출력을 보고 아래 두 값을 직접 넣어 다시 실행하세요:"
  echo "       SPARK_VERSION=x.y.z SCALA_MAJOR_MINOR=2.1x $0"
  exit 1
fi

echo "[INFO] 감지된 Spark 버전: $SPARK_VERSION / Scala: $SCALA_MAJOR_MINOR"
PACKAGE="org.apache.spark:spark-sql-kafka-0-10_${SCALA_MAJOR_MINOR}:${SPARK_VERSION}"
echo "[INFO] 사용할 Kafka 커넥터 패키지: $PACKAGE"

docker cp "$SCRIPT_DIR/posture_sink_stream.py" spark:/opt/spark/posture_sink_stream.py

docker exec -d spark bash -c "/opt/spark/bin/spark-submit \
  --master local[*] \
  --packages ${PACKAGE} \
  /opt/spark/posture_sink_stream.py > /tmp/posture-sink.log 2>&1"

echo "[INFO] posture-sink를 spark 컨테이너 안에서 백그라운드로 시작했습니다."
echo "[INFO] 로그 확인:   docker exec -it spark tail -f /tmp/posture-sink.log"
echo "[INFO] 중지:       docker exec -it spark pkill -f posture_sink_stream.py"
