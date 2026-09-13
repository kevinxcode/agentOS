"""Authenticated, read-only audit history."""

import base64
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select

from agentos.api.routes.auth import Service, require_admin
from agentos.audit.service import record_event, sanitize_metadata
from agentos.auth.models import AdminUser, AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])
PAGE_SIZE = 50
Outcome = Literal["success", "failure", "denied", "error", "rate_limited"]
Admin = Annotated[AdminUser, Depends(require_admin)]


def _encode_cursor(event: AuditEvent) -> str:
    raw = f"{event.created_at.isoformat()}|{event.id}".encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True).decode()
        timestamp, separator, identifier = raw.rpartition("|")
        if not separator:
            raise ValueError
        decoded = datetime.fromisoformat(timestamp), UUID(identifier)
        if _encode_parts(*decoded) != cursor:
            raise ValueError
        return decoded
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Invalid request") from error


def _encode_parts(created_at: datetime, identifier: UUID) -> str:
    raw = f"{created_at.isoformat()}|{identifier}".encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _serialize(event: AuditEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "request_id": event.request_id,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "outcome": event.outcome,
        "safe_metadata": sanitize_metadata(event.safe_metadata),
        "created_at": event.created_at,
    }


@router.get("/events")
async def events(
    service: Service,
    admin: Admin,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    outcome: Annotated[Outcome | None, Query()] = None,
) -> dict[str, object]:
    statement = select(AuditEvent)
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    if outcome is not None:
        statement = statement.where(AuditEvent.outcome == outcome)
    if cursor is not None:
        created_at, identifier = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                AuditEvent.created_at < created_at,
                and_(AuditEvent.created_at == created_at, AuditEvent.id < identifier),
            )
        )
    statement = statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(
        PAGE_SIZE + 1
    )
    snapshot = list((await service.db.scalars(statement)).all())
    page = snapshot[:PAGE_SIZE]
    result: dict[str, object] = {
        "items": [_serialize(event) for event in page],
        "next_cursor": _encode_cursor(page[-1]) if len(snapshot) > PAGE_SIZE else None,
    }

    record_event(
        service.db,
        request_id=service.request_id,
        actor_id=admin.id,
        action="audit.events.viewed",
        outcome="success",
    )
    await service.db.commit()
    return result
