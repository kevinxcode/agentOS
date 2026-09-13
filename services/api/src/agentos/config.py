"""Strict runtime configuration for the AgentOS control plane."""

from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded exclusively from explicit values or ``AGENTOS_*`` keys."""

    model_config = SettingsConfigDict(
        env_prefix="AGENTOS_",
        extra="forbid",
        validate_default=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(min_length=1)
    redis_url: str = Field(min_length=1)
    minio_endpoint: str = Field(min_length=1)
    minio_access_key: str = Field(min_length=1)
    minio_secret_key: str = Field(min_length=1)
    minio_bucket: str = Field(min_length=1)
    session_pepper: str = Field(min_length=32)
    master_key: str = Field(min_length=44)
    auth_proxy_secret: str | None = Field(default=None, min_length=32)
    cookie_secure: bool = True
    readiness_timeout_seconds: float = Field(default=2.0, gt=0)

    @field_validator("master_key")
    @classmethod
    def require_fernet_key(cls, value: str) -> str:
        try:
            Fernet(value.encode("ascii"))
        except (ValueError, UnicodeError):
            raise ValueError("master_key must be a valid Fernet key") from None
        return value

    @field_validator("database_url")
    @classmethod
    def require_async_postgresql_url(cls, value: str) -> str:
        return cls._require_hosted_url(value, {"postgresql+asyncpg"}, "database_url")

    @field_validator("redis_url")
    @classmethod
    def require_redis_url(cls, value: str) -> str:
        return cls._require_hosted_url(value, {"redis", "rediss"}, "redis_url")

    @field_validator("minio_endpoint")
    @classmethod
    def require_http_minio_endpoint(cls, value: str) -> str:
        return cls._require_hosted_url(value, {"http", "https"}, "minio_endpoint")

    @staticmethod
    def _require_hosted_url(value: str, schemes: set[str], field_name: str) -> str:
        try:
            parsed = urlsplit(value)
            parsed.port
        except ValueError:
            parsed = None
        if (
            parsed is None
            or parsed.scheme not in schemes
            or parsed.hostname is None
        ):
            allowed = " or ".join(sorted(schemes))
            raise ValueError(f"{field_name} must include a host and use {allowed}")
        return value

    @model_validator(mode="after")
    def require_secure_production_cookie(self) -> Self:
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("production requires secure cookies")
        if self.environment == "production" and self.auth_proxy_secret is None:
            raise ValueError("production requires an auth proxy secret")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process configuration, caching successful validation."""

    return Settings()  # type: ignore[call-arg]  # Values come from the AGENTOS_ environment.
