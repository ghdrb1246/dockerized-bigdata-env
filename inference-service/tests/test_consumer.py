"""
infer_rule_based()에 대한 단위 테스트 (규칙 기반 골격 검증용).

Kafka/Redis 등 외부 인프라에는 접속하지 않는다 — 순수 함수인
infer_rule_based()만 검증해서 CI(네트워크 없는 GitHub Actions 러너)에서도
빠르고 안정적으로 돌아가게 한다. 실제 LSTM 모델이 붙으면 이 테스트는
infer_rule_based() 대신 모델 추론 함수를 대상으로 확장/교체될 예정이다.
"""
import pytest

from app.consumer import WINDOW_SIZE, infer_rule_based, run_inference
from app.model import MODEL_META_PATH, MODEL_WEIGHTS_PATH


def _event(**overrides):
    base = {
        "sessionId": "session-test",
        "userId": "user-test",
        "deviationScore": 0.0,
        "ruleStatus": "NORMAL",
        "capturedAt": "2026-01-01T00:00:00Z",
        "serverReceivedAt": "2026-01-01T00:00:01Z",
    }
    base.update(overrides)
    return base


def test_high_deviation_score_is_bad():
    result = infer_rule_based(_event(deviationScore=0.72, ruleStatus="COLLAPSED"))
    assert result["inferredStatus"] == "BAD"
    assert result["sessionId"] == "session-test"
    assert result["receivedRuleStatus"] == "COLLAPSED"


def test_mid_deviation_score_is_warning():
    result = infer_rule_based(_event(deviationScore=0.5))
    assert result["inferredStatus"] == "WARNING"


def test_low_deviation_score_is_normal():
    result = infer_rule_based(_event(deviationScore=0.1))
    assert result["inferredStatus"] == "NORMAL"


def test_boundary_values_are_inclusive():
    # 0.7, 0.4는 각각 BAD/WARNING 경계값이며 그 구간에 포함되어야 한다
    assert infer_rule_based(_event(deviationScore=0.7))["inferredStatus"] == "BAD"
    assert infer_rule_based(_event(deviationScore=0.4))["inferredStatus"] == "WARNING"


def test_missing_deviation_score_falls_back_to_received_rule_status():
    result = infer_rule_based(_event(deviationScore=None, ruleStatus="COLLAPSED"))
    assert result["inferredStatus"] == "COLLAPSED"
    assert result["deviationScore"] is None


# --- run_inference()의 세션별 슬라이딩 윈도우 동작 검증 ---
# 매 테스트마다 서로 다른 sessionId를 써서, 모듈 전역 _session_windows에
# 남는 상태가 테스트 간에 서로 영향을 주지 않게 한다.

def test_run_inference_falls_back_to_rule_based_while_window_not_full():
    result = run_inference(_event(sessionId="window-test-1", deviationScore=0.1, featureVector=[0.1, 0.1, 0.1]))
    assert result["model"] == "rule-based-skeleton-v0"
    assert result["windowBuffered"] == 1
    assert result["windowSize"] == WINDOW_SIZE


@pytest.mark.skipif(
    not (MODEL_WEIGHTS_PATH.exists() and MODEL_META_PATH.exists()),
    reason="테스트 모델 파일이 없다 — 먼저 `python train_test_model.py`를 실행해야 한다.",
)
def test_run_inference_switches_to_model_once_window_is_full():
    pytest.importorskip("torch")
    session_id = "window-test-2"
    result = None
    for i in range(WINDOW_SIZE):
        result = run_inference(
            _event(sessionId=session_id, deviationScore=0.1, featureVector=[0.01 * i, 0.0, -0.01 * i])
        )

    assert result["model"] == "test-lstm-v0"
    assert "probabilities" in result
    assert result["inferredStatus"] in {"NORMAL", "WARNING", "BAD"}
