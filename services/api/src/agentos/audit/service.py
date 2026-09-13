"""Append and safely serialize audit outcomes."""

import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agentos.auth.models import AuditEvent

SAFE_METADATA_KEYS = frozenset(
    {
        "category",
        "component",
        "count",
        "detail",
        "method",
        "model",
        "path",
        "provider",
        "reason",
        "resource",
        "status",
        "url",
    }
)
REDACTED = "[REDACTED]"
_URL_SECRET = re.compile(r"(?P<base>(?:https?://|/)[^\s?#]+)(?:[?#][^\s;,]*)")
_CREDENTIAL = re.compile(
    r"(?i)\b(?P<name>password|passwd|secret|token|api[_-]?key|authorization|credential|code)"
    r"(?P<separator>\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s;,]+)"
)
_API_KEY = re.compile(r"(?i)(?<![A-Za-z0-9_-])(?:sk|pk|rk|api)[-_][A-Za-z0-9_-]{12,}")
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}"
    r"(?![A-Za-z0-9_-])"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")
_RECOVERY = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{22}(?![A-Za-z0-9_-])")


def redact_value(value: str) -> str:
    """Remove secret-shaped substrings while retaining useful ordinary prose."""

    value = _URL_SECRET.sub(lambda match: match.group("base"), value)
    value = _CREDENTIAL.sub(
        lambda match: f"{match.group('name')}{match.group('separator')}{REDACTED}", value
    )
    value = _API_KEY.sub(REDACTED, value)
    value = _JWT.sub(REDACTED, value)
    value = _BEARER.sub(f"Bearer {REDACTED}", value)
    return _RECOVERY.sub(REDACTED, value)


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_value(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, Mapping):
        return sanitize_metadata(value)
    return REDACTED


def sanitize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return only explicitly safe keys with secret-shaped values redacted."""

    return {
        key: _safe_value(value)
        for key, value in metadata.items()
        if key in SAFE_METADATA_KEYS
    }


def record_event(
    db: AsyncSession,
    *,
    request_id: str,
    action: str,
    outcome: str,
    actor_id: UUID | None = None,
) -> None:
    db.add(
        AuditEvent(
            request_id=request_id,
            actor_id=actor_id,
            action=action,
            outcome=outcome,
            target_type="admin_user" if actor_id else None,
            target_id=str(actor_id) if actor_id else None,
            safe_metadata={},
        )
    )
