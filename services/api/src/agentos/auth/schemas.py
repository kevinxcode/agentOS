"""Explicit HTTP allowlists: credentials cannot leak through ORM serialization."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from agentos.auth.email import normalize_email


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class CodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    next: Literal["totp_enrollment", "totp_verification"]


class EnrollmentResponse(BaseModel):
    otpauth_uri: str


class ConfirmationResponse(BaseModel):
    recovery_codes: list[str]


class AuthenticatedResponse(BaseModel):
    authenticated: Literal[True] = True


class MeResponse(BaseModel):
    id: UUID
    email: str
    totp_enabled: bool


class AnonymousStateResponse(BaseModel):
    stage: Literal["anonymous"]


class PreauthStateResponse(BaseModel):
    stage: Literal["preauth"]
    next: Literal["totp_enrollment", "totp_verification"]


class FullStateResponse(BaseModel):
    stage: Literal["full"]
    id: UUID
    email: str
    totp_enabled: bool


AuthStateResponse = Annotated[
    AnonymousStateResponse | PreauthStateResponse | FullStateResponse,
    Field(discriminator="stage"),
]
