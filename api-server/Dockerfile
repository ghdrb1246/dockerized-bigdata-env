# ---------- build stage ----------
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
# 의존성만 먼저 받아 레이어 캐싱 (소스 변경 시에도 재다운로드 최소화)
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package

# ---------- runtime stage ----------
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /build/target/api-server.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
