"""
테스트용 LSTM 모델 (하드웨어/빅데이터 플랫폼 파이프라인 검증용).

주의: 이 모델은 실제 자세 데이터로 학습되지 않았다 — `train_test_model.py`가
만든 "합성(synthetic) 예시 키포인트 데이터"로 학습한 테스트 모델이다.
목적은 예측 정확도가 아니라, "LSTM 모델을 실제로 로드하고 추론까지
돌리는 경로(inference-service 컨테이너 자원 사용량, 모델 로딩 시간,
세션별 슬라이딩 윈도우 버퍼링, Kafka 파이프라인과의 통합)에 문제가
없는지"를 검증하는 것이다. 실제 모델(진짜 키포인트 데이터로 학습)이
준비되면 이 파일의 구조(build_model/load_model/predict)는 그대로 두고
`app/models/test_lstm.pt`·`test_lstm.meta.json`만 실제로 학습된
가중치·메타데이터로 교체하면 된다.

torch는 무거운 의존성이라, 설치돼 있지 않거나 가중치 파일이 없어도
서비스 전체가 죽지 않고 규칙 기반(consumer.infer_rule_based)으로
자동 폴백하도록 방어적으로 만들었다 — predict()가 None을 반환하면
호출부가 폴백해야 한다는 신호다.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("inference-service.model")

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_WEIGHTS_PATH = MODEL_DIR / "test_lstm.pt"
MODEL_META_PATH = MODEL_DIR / "test_lstm.meta.json"

# consumer.py의 infer_rule_based()가 쓰는 3단계 분류와 이름을 맞췄다 —
# 나중에 실제 모델이 다른 클래스 체계를 쓰면 이 리스트와
# train_test_model.py를 함께 바꿔야 한다.
CLASS_NAMES = ["NORMAL", "WARNING", "BAD"]

_model = None
_meta = None
_load_lock = threading.Lock()
_load_attempted = False


def _try_import_torch():
    try:
        import torch
        import torch.nn as nn
        return torch, nn
    except ImportError as exc:
        logger.warning(
            "torch가 설치되어 있지 않아 LSTM 모델을 쓸 수 없다 (규칙 기반으로 폴백): %s", exc,
        )
        return None, None


def build_model(nn, input_size: int, hidden_size: int, num_layers: int, num_classes: int):
    """
    PostureLSTM 아키텍처 정의. torch가 없는 환경에서도 이 모듈 자체는
    import 가능해야 해서(FastAPI 앱이 torch 없이도 뜰 수 있게) nn 모듈을
    인자로 받아 지연 정의한다 — 최상위에서 `class PostureLSTM(nn.Module)`
    처럼 바로 정의하면 import 시점에 torch가 없을 때 곧장 에러가 난다.
    """

    class PostureLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
            )
            self.classifier = nn.Linear(hidden_size, num_classes)

        def forward(self, x):
            # x: (batch, window, input_size)
            _, (h_n, _) = self.lstm(x)
            last_hidden = h_n[-1]  # 마지막 레이어의 마지막 시점 hidden state, (batch, hidden_size)
            return self.classifier(last_hidden)

    return PostureLSTM()


def load_model():
    """
    모델 가중치를 최초 1회만 로드해 전역에 캐싱한다(이벤트마다 다시
    로드하지 않음). torch가 없거나 가중치 파일이 없으면 (None, None)을
    반환하고 호출부(consumer.run_inference)가 규칙 기반으로 폴백한다.
    """
    global _model, _meta, _load_attempted

    with _load_lock:
        if _load_attempted:
            return _model, _meta
        _load_attempted = True

        torch, nn = _try_import_torch()
        if torch is None:
            return None, None

        if not MODEL_WEIGHTS_PATH.exists() or not MODEL_META_PATH.exists():
            logger.warning(
                "테스트 모델 파일을 찾을 수 없어 규칙 기반으로 폴백한다 "
                "(weights=%s, meta=%s). `python train_test_model.py`를 먼저 "
                "실행해 테스트 모델을 만들어야 한다.",
                MODEL_WEIGHTS_PATH, MODEL_META_PATH,
            )
            return None, None

        try:
            with open(MODEL_META_PATH) as f:
                meta = json.load(f)

            model = build_model(
                nn,
                input_size=meta["input_size"],
                hidden_size=meta["hidden_size"],
                num_layers=meta["num_layers"],
                num_classes=len(CLASS_NAMES),
            )
            state_dict = torch.load(MODEL_WEIGHTS_PATH, map_location="cpu", weights_only=True)
            model.load_state_dict(state_dict)
            model.eval()

            _model, _meta = model, meta
            logger.info(
                "테스트 LSTM 모델 로드 완료 (input_size=%s, hidden_size=%s, window_size=%s)",
                meta["input_size"], meta["hidden_size"], meta["window_size"],
            )
        except Exception:
            logger.exception("모델 로드 실패, 규칙 기반으로 폴백한다")
            _model, _meta = None, None

        return _model, _meta


def predict(window: list) -> Optional[dict]:
    """
    window: 길이 WINDOW_SIZE인 featureVector 시퀀스(각 원소는 float 리스트).
    모델/가중치를 쓸 수 없으면 None을 반환한다 — 호출부는 이 경우
    infer_rule_based()로 폴백해야 한다.
    """
    model, meta = load_model()
    if model is None:
        return None

    torch, _ = _try_import_torch()
    input_size = meta["input_size"]

    def _fit(vec):
        # featureVector 길이가 학습 시점(input_size)과 다를 수 있어(실제
        # 키포인트 수가 아직 확정 안 됨) 0으로 패딩하거나 잘라서 맞춘다.
        # 테스트 모델 단계의 방어적 처리이며, 실제 모델에서는 전처리
        # 파이프라인에서 이 부분을 명확히 고정해야 한다.
        vec = [float(v) for v in vec][:input_size]
        return vec + [0.0] * (input_size - len(vec))

    fitted = [_fit(v) for v in window]

    with torch.no_grad():
        x = torch.tensor([fitted], dtype=torch.float32)  # (1, window, input_size)
        logits = model(x)
        probs = torch.softmax(logits, dim=-1)[0].tolist()

    predicted_idx = max(range(len(probs)), key=lambda i: probs[i])
    return {
        "inferredStatus": CLASS_NAMES[predicted_idx],
        "probabilities": {name: round(p, 4) for name, p in zip(CLASS_NAMES, probs)},
        "model": "test-lstm-v0",
    }


def status() -> dict:
    """
    `/health`(main.py)에서 로그를 안 뒤져도 모델 로드 상태를 바로 볼 수
    있게 하는 헬퍼. load_model()과 마찬가지로 최초 1회만 실제 로드를
    시도하고, 이후에는 캐시된 결과만 요약해서 돌려준다 — 매 헬스체크
    요청마다 다시 로드하지 않는다.
    """
    model, meta = load_model()
    if model is not None:
        return {
            "loaded": True,
            "inputSize": meta["input_size"],
            "hiddenSize": meta["hidden_size"],
            "windowSize": meta["window_size"],
        }

    torch, _ = _try_import_torch()
    if torch is None:
        reason = "torch가 설치되어 있지 않음"
    elif not MODEL_WEIGHTS_PATH.exists() or not MODEL_META_PATH.exists():
        reason = "테스트 모델 파일(test_lstm.pt/.meta.json)을 찾을 수 없음"
    else:
        reason = "모델 로드 중 예외 발생 (자세한 원인은 기동 로그의 ERROR 확인)"

    return {"loaded": False, "reason": reason}
