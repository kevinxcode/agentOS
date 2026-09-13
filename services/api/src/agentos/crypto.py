"""Focused cryptographic primitives for authentication material."""

import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type
from cryptography.fernet import Fernet

_ARGON2ID = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    """Return an Argon2id password hash."""

    return _ARGON2ID.hash(password)


def verify_password(encoded_hash: str, password: str) -> bool:
    """Verify a password without exposing malformed-hash details."""

    try:
        return _ARGON2ID.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def hash_recovery_code(code: str) -> str:
    """Return an Argon2id recovery-code hash."""

    return _ARGON2ID.hash(code)


def verify_recovery_code(encoded_hash: str, code: str) -> bool:
    """Verify a one-time recovery code."""

    return verify_password(encoded_hash, code)


def hash_token(token: str, session_pepper: str) -> str:
    """Return a keyed, deterministic digest for an opaque session token."""

    return hmac.new(
        session_pepper.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class SecretCipher:
    """Encrypt and decrypt secret bytes using the configured Fernet master key."""

    def __init__(self, master_key: str) -> None:
        self._fernet = Fernet(master_key.encode("ascii"))

    def encrypt_secret(self, secret: bytes) -> bytes:
        """Encrypt secret material for storage."""

        return self._fernet.encrypt(secret)

    def decrypt_secret(self, encrypted_secret: bytes) -> bytes:
        """Decrypt previously stored secret material."""

        return self._fernet.decrypt(encrypted_secret)
