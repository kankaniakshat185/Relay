"""At-rest encryption for connector tokens.

`connector_credentials` rows hold real GitHub/Slack/Jira access tokens —
unlike the login flow (ADR 0003), these grant broad read access to a
user's actual data, so they aren't stored as plaintext columns.
`CONNECTOR_ENCRYPTION_KEY` is deliberately a separate key from
`SECRET_KEY` (which signs login session JWTs) — different purpose,
different rotation story.
"""

from cryptography.fernet import Fernet, InvalidToken

from relay_api.core.config import get_settings


class TokenDecryptionError(Exception):
    """Raised when a stored token can't be decrypted (wrong/rotated key)."""


def _fernet() -> Fernet:
    return Fernet(get_settings().connector_encryption_key.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenDecryptionError("stored token could not be decrypted") from exc
