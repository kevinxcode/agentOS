import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.config import Settings, get_settings
from agentos.crypto import SecretCipher
from agentos.db import create_database


def valid_settings() -> dict[str, object]:
    return {
        "environment": "test",
        "database_url": "postgresql+asyncpg://u:p@db/app",
        "redis_url": "redis://redis:6379/0",
        "minio_endpoint": "http://minio:9000",
        "minio_access_key": "access-key",
        "minio_secret_key": "secret-key",
        "minio_bucket": "agentos",
        "session_pepper": "x" * 32,
        "master_key": Fernet.generate_key().decode("ascii"),
    }


def test_settings_key_constructs_real_cipher() -> None:
    settings = Settings(**valid_settings())
    cipher = SecretCipher(settings.master_key)
    assert cipher.decrypt_secret(cipher.encrypt_secret(b"seed")) == b"seed"


@pytest.mark.parametrize("key", ["x" * 44, "!" * 44, "é" * 44])
def test_settings_reject_non_fernet_master_key(key: str) -> None:
    values = valid_settings()
    values["master_key"] = key
    with pytest.raises(ValidationError, match="Fernet"):
        Settings(**values)


def test_production_rejects_insecure_cookie() -> None:
    values = valid_settings()
    values.update(environment="production", cookie_secure=False)

    with pytest.raises(ValidationError, match="secure cookies"):
        Settings(**values)


def test_production_requires_a_strong_auth_proxy_secret() -> None:
    values = valid_settings()
    values["environment"] = "production"

    with pytest.raises(ValidationError, match="auth proxy secret"):
        Settings(**values)

    values["auth_proxy_secret"] = "short"
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(**values)

    values["auth_proxy_secret"] = "s" * 32
    assert Settings(**values).auth_proxy_secret == "s" * 32


def test_get_settings_reads_the_agentos_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in valid_settings().items():
        monkeypatch.setenv(f"AGENTOS_{name.upper()}", str(value))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.environment == "test"
    assert settings.database_url == "postgresql+asyncpg://u:p@db/app"
    assert settings.minio_bucket == "agentos"
    get_settings.cache_clear()


def test_settings_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Settings(**valid_settings(), unknown_setting="value")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql+asyncpg:///app"),
        ("database_url", "postgresql+asyncpg://"),
        ("redis_url", "redis:///0"),
        ("redis_url", "redis://"),
        ("minio_endpoint", "http:///bucket"),
        ("minio_endpoint", "not-a-url"),
    ],
)
def test_settings_reject_malformed_or_hostless_urls(field: str, value: str) -> None:
    values = valid_settings()
    values[field] = value

    with pytest.raises(ValidationError, match="must include a host"):
        Settings(**values)


def test_readiness_timeout_must_be_positive() -> None:
    values = valid_settings()
    values["readiness_timeout_seconds"] = 0

    with pytest.raises(ValidationError, match="greater than 0"):
        Settings(**values)


def test_readiness_timeout_is_configurable() -> None:
    values = valid_settings()
    values["readiness_timeout_seconds"] = 0.25

    assert Settings(**values).readiness_timeout_seconds == 0.25


@pytest.mark.asyncio
async def test_database_configuration_is_app_scoped_and_does_not_connect() -> None:
    first = create_database("postgresql+asyncpg://u:p@first.invalid/app")
    second = create_database("postgresql+asyncpg://u:p@second.invalid/app")

    first_session = first.session_factory()
    second_session = second.session_factory()
    assert isinstance(first_session, AsyncSession)
    assert first_session.bind is first.engine
    assert second_session.bind is second.engine
    assert first.session_factory is not second.session_factory

    await first_session.close()
    await second_session.close()
    await first.close()
    await second.close()
