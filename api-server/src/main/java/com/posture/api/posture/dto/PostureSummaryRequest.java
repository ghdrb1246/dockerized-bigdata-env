package com.posture.api.posture.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import java.time.Instant;
import java.util.List;

/**
 * 클라이언트(브라우저)가 1~2Hz 주기로 전송하는 자세 요약 이벤트.
 *
 * 아키텍처 원칙(Posture_Architecture_v3_MVP_Vision.md §2.A.1):
 *   - 원본 영상 프레임은 절대 포함하지 않는다.
 *   - 기준 자세 대비 정규화된 키포인트/특징값 요약만 전송한다.
 *
 * 인증(사용자 식별)은 다음 단계에서 붙이며, 지금은 userId를 그대로
 * 받는 헬스체크~1차 파이프라인 검증 수준의 골격이다.
 */
public record PostureSummaryRequest(

        @NotBlank(message = "sessionId는 필수입니다.")
        String sessionId,

        @NotBlank(message = "userId는 필수입니다.")
        String userId,

        /** 클라이언트에서 이 요약을 측정한 시각 (ISO-8601). 생략 시 서버 수신 시각으로 대체. */
        Instant capturedAt,

        /** 정규화된 키포인트 기반 특징 벡터 (원본 좌표가 아닌 기준 자세 대비 정규화 값). */
        @NotEmpty(message = "featureVector는 비어 있을 수 없습니다.")
        List<Double> featureVector,

        /** 기준 자세 대비 편차 점수 (클라이언트 1차 규칙 기반 계산값). */
        @NotNull(message = "deviationScore는 필수입니다.")
        @DecimalMin(value = "0.0", message = "deviationScore는 0 이상이어야 합니다.")
        @DecimalMax(value = "1.0", message = "deviationScore는 1 이하여야 합니다.")
        Double deviationScore,

        /** 클라이언트 1차 규칙 기반 상태 코드: NORMAL(바른자세) 또는 COLLAPSED(자세붕괴 후보). */
        @NotBlank(message = "ruleStatus는 필수입니다.")
        @Pattern(regexp = "NORMAL|COLLAPSED", message = "ruleStatus는 NORMAL 또는 COLLAPSED 중 하나여야 합니다.")
        String ruleStatus,

        /** 표본 추출 주기(Hz). 생략 가능(계획서 기준 기본 10Hz). */
        Double sampleRateHz
) {
}
