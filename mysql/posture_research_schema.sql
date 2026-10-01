-- =====================================================================
-- 연구DB (posture_research) 스키마
--
-- 계획서 "데이터베이스" 절 정의:
--   연구 DB: 수집 참가자, 수집 세션, 라벨, 데이터셋 분할, 모델 평가
--   결과 등
--
-- posture_app(서비스DB)과 완전히 분리된 DB다. api-server는 이 DB에
-- 접속하지 않는다 — 오프라인으로 수집한 파일럿/라벨링 데이터(예:
-- posture-pilot-P01.csv)를 적재하고, 나중에 LSTM 학습/평가에 쓰는
-- 연구용 DB다. posture-pilot 수집 CSV 스키마(56개 컬럼, MediaPipe
-- Pose 33 landmark 포함)를 그대로 반영했다.
--
-- MySQL Workbench에서: File > Open SQL Script > 이 파일 선택 >
-- Execute (⚡).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS posture_research
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE posture_research;

-- ---------------------------------------------------------------------
-- participants: 수집 참가자 (posture-pilot CSV의 participant_code).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS participants (
    participant_code VARCHAR(32) NOT NULL,
    created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (participant_code)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- collection_sessions: 수집 세션 (posture-pilot CSV의 capture_id 1건 =
-- 이 테이블 1행). 세션 단위 메타데이터(장비/과제 설정)만 담고, 프레임
-- 단위 상세는 posture_samples에 둔다.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collection_sessions (
    capture_id              VARCHAR(64)  NOT NULL,
    participant_code        VARCHAR(32)  NOT NULL,
    schema_version          VARCHAR(32)  NULL,
    started_at              DATETIME(3)  NOT NULL,
    pose_model               VARCHAR(128) NULL,
    feature_version          VARCHAR(32)  NULL,
    calibration_seconds      DOUBLE       NULL,
    target_sample_hz         DOUBLE       NULL,
    task_id                  VARCHAR(32)  NULL,
    activity                 VARCHAR(32)  NULL,
    requested_head_direction VARCHAR(32)  NULL,
    requested_posture        VARCHAR(32)  NULL,
    requested_presence       VARCHAR(32)  NULL,
    repetition                INT          NULL,
    planned_seconds           DOUBLE       NULL,
    camera_view                VARCHAR(32)  NULL,
    camera_height               VARCHAR(32)  NULL,
    distance_cm                  DOUBLE       NULL,
    desk_layout                   VARCHAR(32)  NULL,
    stop_reason                    VARCHAR(32)  NULL,
    calibration_id                  VARCHAR(64)  NULL,
    width                             INT          NULL,
    height                             INT          NULL,
    delegate                           VARCHAR(16)  NULL, -- GPU/CPU
    review_status                       VARCHAR(32)  NULL,
    pose_training_eligible                TINYINT(1)   NULL,
    sample_count                          BIGINT       NOT NULL DEFAULT 0,
    loaded_at                              DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (capture_id),
    KEY idx_collection_participant (participant_code, started_at),
    CONSTRAINT fk_collection_participant
        FOREIGN KEY (participant_code) REFERENCES participants(participant_code)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- posture_samples: 프레임(표본) 단위 원자료. posture-pilot CSV 1행 =
-- 이 테이블 1행. 10Hz 기준 1분 세션이면 약 600행 — 대량 적재 성능
-- 테스트(큰 데이터 입력)의 실제 대상 테이블이다. landmarks_json /
-- world_landmarks_json은 MediaPipe Pose 33 keypoint 배열을 CSV 원본
-- 그대로 JSON으로 보관한다(굳이 33개 컬럼으로 펼치지 않음 — 스키마가
-- MediaPipe 버전에 따라 흔들릴 수 있어 원문 보존이 더 안전).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS posture_samples (
    id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
    capture_id            VARCHAR(64)  NOT NULL,
    sample_index          INT          NOT NULL,
    elapsed_ms            DOUBLE       NOT NULL,
    video_time_ms         DOUBLE       NULL,
    gap_ms                DOUBLE       NULL,
    segment_id            VARCHAR(32)  NULL,
    manual_label          VARCHAR(32)  NULL,
    label_source          VARCHAR(32)  NULL,
    measurement_quality   VARCHAR(16)  NULL,
    head_gap              DOUBLE       NULL,
    lateral_offset        DOUBLE       NULL,
    shoulder_tilt         DOUBLE       NULL,
    visibility            DOUBLE       NULL,
    baseline_head_gap     DOUBLE       NULL,
    baseline_offset       DOUBLE       NULL,
    baseline_tilt         DOUBLE       NULL,
    delta_head_gap        DOUBLE       NULL,
    delta_offset          DOUBLE       NULL,
    delta_tilt            DOUBLE       NULL,
    rule_score            DOUBLE       NULL,
    rule_prediction       VARCHAR(16)  NULL, -- normal | deviation
    threshold             DOUBLE       NULL,
    hold_seconds          DOUBLE       NULL,
    realert_seconds       DOUBLE       NULL,
    recover_seconds       DOUBLE       NULL,
    inference_ms          DOUBLE       NULL,
    pose_detected         TINYINT(1)   NULL,
    landmark_count        INT          NULL,
    landmarks_json        JSON         NULL,
    world_landmarks_json  JSON         NULL,
    KEY idx_samples_capture (capture_id, sample_index),
    CONSTRAINT fk_samples_capture
        FOREIGN KEY (capture_id) REFERENCES collection_sessions(capture_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- dataset_splits: 학습/검증/평가 데이터셋 분할 배정 (세션 단위).
-- 다음 단계(실제 학습 파이프라인 연결) 과제 — 지금은 구조만.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dataset_splits (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    capture_id   VARCHAR(64)  NOT NULL,
    split        VARCHAR(16)  NOT NULL, -- train | val | test
    assigned_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_split_capture (capture_id),
    CONSTRAINT fk_split_capture
        FOREIGN KEY (capture_id) REFERENCES collection_sessions(capture_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- model_evaluations: 모델 버전별 평가 결과 (F1/AUROC, 이벤트 단위
-- 오경보율·지연시간 등). 다음 단계 과제 — 지금은 구조만.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_evaluations (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    model_version VARCHAR(64)  NOT NULL,
    evaluated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    metric_name   VARCHAR(64)  NOT NULL,
    metric_value  DOUBLE       NOT NULL,
    notes         VARCHAR(255) NULL,
    KEY idx_eval_model (model_version, metric_name)
) ENGINE=InnoDB;
