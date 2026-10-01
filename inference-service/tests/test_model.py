"""
app/model.py에 대한 테스트. 실제로 train_test_model.py로 학습한
가중치(app/models/test_lstm.pt, test_lstm.meta.json)가 저장소에
포함되어 있다는 전제로 동작한다 — CI에서도 requirements.txt의 torch
설치 후 이 파일들을 그대로 읽어 추론까지 해본다(느리지만 가벼운
모델이라 수 초 내로 끝남).
"""
import pytest

from app.model import CLASS_NAMES, MODEL_META_PATH, MODEL_WEIGHTS_PATH, predict

torch = pytest.importorskip("torch")

pytestmark = pytest.mark.skipif(
    not (MODEL_WEIGHTS_PATH.exists() and MODEL_META_PATH.exists()),
    reason="테스트 모델 파일이 없다 — 먼저 `python train_test_model.py`를 실행해야 한다.",
)


def _sequence(base_noise: float, drift: float, window_size: int = 10, size: int = 3) -> list:
    import random

    random.seed(0)
    seq = []
    value = [0.0] * size
    for t in range(window_size):
        value = [v + random.uniform(-base_noise, base_noise) + drift * (t / window_size) for v in value]
        seq.append(value)
    return seq


def test_predict_returns_known_class_and_valid_probabilities():
    window = _sequence(base_noise=0.02, drift=0.0)  # NORMAL 패턴과 같은 분포
    result = predict(window)

    assert result is not None
    assert result["inferredStatus"] in CLASS_NAMES
    assert set(result["probabilities"].keys()) == set(CLASS_NAMES)
    total = sum(result["probabilities"].values())
    assert 0.98 <= total <= 1.02  # softmax 확률 합은 1에 가까워야 함(반올림 오차 허용)
    assert result["model"] == "test-lstm-v0"


def test_predict_handles_feature_vector_length_mismatch():
    # 학습 시 input_size=3인데, 길이가 다른 featureVector가 들어와도
    # (패딩/절단으로) 예외 없이 결과를 반환해야 한다.
    window = [[0.1, 0.2] for _ in range(10)]  # 길이 2 (학습보다 짧음)
    result = predict(window)
    assert result is not None
    assert result["inferredStatus"] in CLASS_NAMES
