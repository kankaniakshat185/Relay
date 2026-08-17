"""Session token creation/verification.

Relay has no passwords — the session token is the only credential a
browser holds, minted after a successful login OAuth flow (see `auth/`).
It carries identity only; it is never used for connector data access
(see `connectors/`, which hold their own scoped credentials).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from relay_api.core.config import get_settings

_ALGORITHM = "HS256"


class InvalidSessionToken(Exception):
    """Raised when a session token is missing, expired, or fails verification."""


def create_session_token(user_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=settings.session_token_ttl_seconds),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def verify_session_token(token: str) -> UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidSessionToken(str(exc)) from exc

    subject = payload.get("sub")
    if not subject:
        raise InvalidSessionToken("token missing subject")

    try:
        return UUID(subject)
    except ValueError as exc:
        raise InvalidSessionToken("token subject is not a valid user id") from exc
