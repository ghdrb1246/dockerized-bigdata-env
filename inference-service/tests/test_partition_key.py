"""
posture.inference 메시지 키(D-15) 단위 테스트.

파티션을 여러 개로 늘린 뒤에도 같은 사용자(세션)의 추론 결과가 항상
같은 파티션으로 가야 api-server 상태머신의 판정 순서가 지켜진다.
"""
from app.consumer import _partition_key


def test_key_is_user_id():
    assert _partition_key({"userId": "P01", "sessionId": "s-1"}) == "P01"


def test_falls_back_to_session_id_when_user_id_missing():
    assert _partition_key({"userId": None, "sessionId": "s-1"}) == "s-1"
    assert _partition_key({"userId": "", "sessionId": "s-1"}) == "s-1"


def test_none_when_both_missing():
    assert _partition_key({}) is None
