package com.posture.api.posture.cep;

/**
 * {@code posture.inference} 토픽 메시지에서 상태머신 판정에 필요한 필드만
 * 뽑아낸 뷰.
 *
 * inference-service(Python)가 발행하는 JSON은 이 레코드에 없는 필드도
 * 더 담고 있다({@code probabilities}, {@code model}, {@code windowSize}
 * 등) — v4 메시지 규격 9장 원칙("소비자는 모르는 필드를 무시해야 한다")에
 * 따라 {@link PostureInferenceConsumer}가 원시 JSON을 Map으로 파싱한 뒤
 * 필요한 필드만 꺼내 이 레코드를 만든다.
 */
public record InferenceEvent(
        String sessionId,
        String userId,
        String inferredStatus,
        String capturedAt
) {
}
