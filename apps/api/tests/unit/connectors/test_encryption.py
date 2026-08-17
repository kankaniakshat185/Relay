import pytest

from relay_api.connectors.encryption import TokenDecryptionError, decrypt_token, encrypt_token


def test_round_trips_a_token() -> None:
    plaintext = "gho_super_secret_access_token"

    ciphertext = encrypt_token(plaintext)

    assert ciphertext != plaintext
    assert decrypt_token(ciphertext) == plaintext


def test_rejects_garbage_ciphertext() -> None:
    with pytest.raises(TokenDecryptionError):
        decrypt_token("not-actually-encrypted")
