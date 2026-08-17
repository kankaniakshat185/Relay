import uuid

import jwt
import pytest

from relay_api.core.security import InvalidSessionToken, create_session_token, verify_session_token


def test_round_trips_user_id() -> None:
    user_id = uuid.uuid4()

    token = create_session_token(user_id)

    assert verify_session_token(token) == user_id


def test_rejects_garbage_token() -> None:
    with pytest.raises(InvalidSessionToken):
        verify_session_token("not-a-real-token")


def test_rejects_token_missing_subject() -> None:
    from relay_api.core.config import get_settings

    token = jwt.encode({"iat": 0}, get_settings().secret_key, algorithm="HS256")

    with pytest.raises(InvalidSessionToken):
        verify_session_token(token)
