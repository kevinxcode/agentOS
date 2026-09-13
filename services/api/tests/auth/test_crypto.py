import pytest
from argon2 import extract_parameters
from argon2.low_level import Type
from cryptography.fernet import Fernet, InvalidToken

from agentos.crypto import (
    SecretCipher,
    hash_password,
    hash_recovery_code,
    hash_token,
    verify_password,
    verify_recovery_code,
)


def test_password_hash_is_argon2id_and_verifies() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "correct horse battery staple") is True
    assert verify_password(encoded, "wrong") is False


def test_password_verification_rejects_malformed_hashes() -> None:
    assert verify_password("not-an-argon2-hash", "password") is False


def test_recovery_codes_use_argon2id_and_verify() -> None:
    encoded = hash_recovery_code("recovery-code")

    assert encoded.startswith("$argon2id$")
    assert verify_recovery_code(encoded, "recovery-code") is True
    assert verify_recovery_code(encoded, "different-code") is False


def test_token_hash_is_keyed_deterministic_hmac_sha256() -> None:
    digest = hash_token("opaque-session-token", "session-pepper-value-that-is-long")

    assert digest == "d21e8d5c2950468833319249913f8b79c8977672c79f28a3057daa51f3146e84"
    assert hash_token("different-token", "session-pepper-value-that-is-long") != digest
    assert hash_token("opaque-session-token", "different-pepper-value-that-is-long") != digest


def test_secret_ciphertext_does_not_contain_plaintext() -> None:
    cipher = SecretCipher(Fernet.generate_key().decode("ascii"))

    encrypted = cipher.encrypt_secret(b"totp-secret")

    assert b"totp-secret" not in encrypted
    assert cipher.decrypt_secret(encrypted) == b"totp-secret"


def test_cipher_authenticates_ciphertext_and_randomizes_encryption() -> None:
    cipher = SecretCipher(Fernet.generate_key().decode("ascii"))
    first = cipher.encrypt_secret(b"seed")
    assert first != cipher.encrypt_secret(b"seed")
    with pytest.raises(InvalidToken):
        cipher.decrypt_secret(first[:-5] + b"wrong")
    with pytest.raises(InvalidToken):
        SecretCipher(Fernet.generate_key().decode("ascii")).decrypt_secret(first)


@pytest.mark.parametrize("key", ["", "x" * 44, "!" * 44])
def test_cipher_rejects_invalid_key(key: str) -> None:
    with pytest.raises(ValueError):
        SecretCipher(key)


@pytest.mark.parametrize("hasher", [hash_password, hash_recovery_code])
def test_argon2_has_strong_costs_and_independent_salts(hasher) -> None:
    first, second = hasher("same-value"), hasher("same-value")
    parameters = extract_parameters(first)
    assert parameters.type is Type.ID
    assert parameters.memory_cost >= 65536
    assert parameters.time_cost >= 3
    assert parameters.parallelism >= 1
    assert parameters.salt_len >= 16
    assert parameters.hash_len >= 32
    assert first.split("$")[4] != second.split("$")[4]
