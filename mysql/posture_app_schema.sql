-- =====================================================================
-- 서비스DB (posture_app) 스키마
--
-- 계획서 "데이터베이스" 절 정의:
--   서비스 DB: 계정, 기준 자세, 측정 세션, 붕괴 이벤트, 기간 통계 등
--
-- 이 DB는 api-server(Spring Boot)와 posture-cep(Python)가 실시간으로
-- 쓰는 "운영" 데이터베이스다. 원본 영상/키포인트 시계열 전체는 여기
-- 저장하지 않는다(그건 HDFS 몫) — 여기는 세션 메타데이터와 확정된
-- 붕괴 이벤트, 이후 집계될 기간 통계만 다룬다.
--
-- .env.example 기준 기본 접속 정보와 DB명이 일치한다
-- (DB_NAME=posture_app). MySQL Workbench에서 이 스크립트를 그대로
-- 실행하면 된다: File > Open SQL Script > 이 파일 선택 > Execute (⚡).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS posture_app
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE posture_app;

-- ---------------------------------------------------------------------
-- accounts: 계정 (인증은 다음 단계 과제 — 지금은 세션이 참조할 최소
-- 골격만 둔다. user_id는 지금 단계에서는 클라이언트가 자유 문자열로
-- 보내는 값을 그대로 쓰고 있어 FK 제약은 걸지 않는다.)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    user_id      VARCHAR(64)  NOT NULL,
    display_name VARCHAR(100) NULL,
    created_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (user_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- baseline_postures: 기준 자세 (사용자가 캘리브레이션한 기준값 — 지금
-- 단계에서는 클라이언트가 기준 자세 대비 델타를 이미 계산해 보내고
-- 있어 서버가 별도로 쓰지는 않는다. 다음 단계(서버 측 보정/재계산)를
-- 위한 자리만 마련해둔다.)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS baseline_postures (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       VARCHAR(64)  NOT NULL,
    captured_at   DATETIME(3)  NOT NULL,
    feature_json  JSON         NOT NULL,
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_baseline_user (user_id, captured_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- sessions: 측정 세션. api-server가 posture.summary 이벤트를 받을
-- 때마다 (sessionId, userId) 기준으로 upsert한다 — 최초 수신 시각을
-- started_at, 매 수신마다 last_seen_at/sample_count를 갱신.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id    VARCHAR(64)  NOT NULL,
    user_id       VARCHAR(64)  NOT NULL,
    started_at    DATETIME(3)  NOT NULL,
    last_seen_at  DATETIME(3)  NOT NULL,
    ended_at      DATETIME(3)  NULL,
    sample_count  BIGINT       NOT NULL DEFAULT 0,
    status        VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE', -- ACTIVE | ENDED
    PRIMARY KEY (session_id),
    KEY idx_sessions_user (user_id, started_at)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- collapse_events: posture-cep이 확정(EVENT_STARTED)·갱신(RE_ALERT)·
-- 종료(EVENT_ENDED)한 자세 붕괴 이벤트. posture-cep의
-- PostureCepEngine이 만드는 이벤트 dict와 1:1로 대응한다.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collapse_events (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id        VARCHAR(64)  NOT NULL,
    user_id           VARCHAR(64)  NOT NULL,
    started_at        DATETIME(3)  NOT NULL,
    ended_at          DATETIME(3)  NULL,
    duration_seconds  DOUBLE       NULL,
    alert_count       INT          NOT NULL DEFAULT 1,
    last_alert_at     DATETIME(3)  NOT NULL,
    recovered         TINYINT(1)   NOT NULL DEFAULT 0,
    ongoing           TINYINT(1)   NOT NULL DEFAULT 1,
    updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                                    ON UPDATE CURRENT_TIMESTAMP(3),
    -- posture-cep은 이벤트 자체의 DB PK를 모르는 채로(자기 메모리
    -- 상태만 들고) EVENT_STARTED -> RE_ALERT -> EVENT_ENDED를 순서대로
    -- 기록한다. (session_id, started_at) 조합이 같은 붕괴 이벤트를
    -- 가리키는 자연키이므로 UNIQUE로 두고 INSERT ... ON DUPLICATE KEY
    -- UPDATE로 매번 같은 행을 갱신한다.
    UNIQUE KEY uq_collapse_session_started (session_id, started_at),
    KEY idx_collapse_user (user_id, started_at),
    KEY idx_collapse_ongoing (ongoing)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- period_stats: 기간별 집계(바른 자세 유지율, 시간당 붕괴 횟수 등).
-- 계획서 "주기 분석과 통계 산출" 절 대응 — 실제 집계 배치(Spark 또는
-- 스케줄 쿼리)는 다음 단계 과제. 지금은 조회 API가 참조할 테이블
-- 구조만 미리 만들어둔다.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS period_stats (
    id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id               VARCHAR(64)  NOT NULL,
    period_start          DATETIME(3)  NOT NULL,
    period_end            DATETIME(3)  NOT NULL,
    valid_seconds         DOUBLE       NOT NULL,
    normal_ratio          DOUBLE       NULL,
    collapse_count        INT          NOT NULL DEFAULT 0,
    collapse_per_hour     DOUBLE       NULL,
    avg_duration_seconds  DOUBLE       NULL,
    median_duration_seconds DOUBLE     NULL,
    model_version         VARCHAR(64)  NULL,
    computed_at           DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_period_user (user_id, period_start)
) ENGINE=InnoDB;
