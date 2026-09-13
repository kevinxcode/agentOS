"""Security and pagination contracts for the read-only audit API."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from agentos.api.app import create_app
from agentos.auth.models import AdminUser, AuditEvent, Session
from agentos.config import Settings
from agentos.crypto import hash_password, hash_token
from agentos.db import Base, create_database

PAGE_SIZE = 50
FULL_TOKEN = "f" * 43
PREAUTH_TOKEN = "p" * 43


@pytest_asyncio.fixture
async def audit_context(tmp_path) -> AsyncIterator[tuple[AsyncClient, object, AdminUser]]:
    settings = Settings(
        environment="test",
        database_url="postgresql+asyncpg://u:p@db/app",
        redis_url="redis://redis:6379/0",
        minio_endpoint="http://minio:9000",
        minio_access_key="key",
        minio_secret_key="secret",
        minio_bucket="agentos",
        session_pepper="p" * 32,
        master_key=Fernet.generate_key().decode(),
        cookie_secure=True,
    )
    database = create_database(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC)
    async with database.session_factory() as db:
        admin = AdminUser(email="admin@example.com", password_hash=hash_password("password"))
        db.add(admin)
        await db.flush()
        for token, stage in ((FULL_TOKEN, "full"), (PREAUTH_TOKEN, "preauth")):
            db.add(
                Session(
                    admin_user_id=admin.id,
                    token_hash=hash_token(token, settings.session_pepper),
                    stage=stage,
                    expires_at=now + timedelta(hours=1),
                    last_seen_at=now,
                    ip_hash="i" * 64,
                    user_agent_hash="u" * 64,
                    created_at=now,
                )
            )
        await db.commit()

    app = create_app(settings=settings, readiness_checks={})
    async with app.router.lifespan_context(app):
        app.state.session_factory = database.session_factory
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as api:
            yield api, database, admin
    await database.close()


def authenticated(api: AsyncClient, token: str = FULL_TOKEN) -> None:
    api.cookies.set("agentos_session", token)


@pytest.mark.asyncio
async def test_audit_requires_a_current_full_session(audit_context) -> None:
    api, _, _ = audit_context
    assert (await api.get("/audit/events")).status_code == 401

    authenticated(api, PREAUTH_TOKEN)
    response = await api.get("/audit/events")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required or credentials invalid"}


@pytest.mark.asyncio
async def test_audit_allowlists_metadata_and_redacts_secret_shaped_values(audit_context) -> None:
    api, database, admin = audit_context
    created_at = datetime(2030, 1, 1, 12, tzinfo=UTC)
    unsafe_values = {
        "api": "sk-secret-api-key-1234567890",
        "assignment": "password=hunter2",
        "bearer": "Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.deadbeef",
        "callback": "callback code=super-secret-code",
        "recovery": "abcdefghijklmnopqrstuv",
    }
    ordinary = "Bearer authentication is disabled; customer #42 submitted a question"
    async with database.session_factory() as db:
        await db.execute(delete(AuditEvent))
        db.add(
            AuditEvent(
                id=UUID("00000000-0000-0000-0000-000000000001"),
                request_id="request-visible",
                actor_id=admin.id,
                action="agent.question.submitted",
                target_type="task",
                target_id="42",
                outcome="success",
                safe_metadata={
                    "detail": ordinary + "; " + "; ".join(unsafe_values.values()),
                    "path": "/oauth/callback?code=path-secret#private",
                    "url": "https://agentos.example/tasks/42?token=query-secret#private",
                    "password": "top-secret",
                    "session_token": "session-secret",
                    "totp_secret": "totp-secret",
                    "unknown": "must not be serialized",
                },
                created_at=created_at,
            )
        )
        await db.commit()

    authenticated(api)
    response = await api.get("/audit/events", params={"action": "agent.question.submitted"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["next_cursor"] is None
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert set(item) == {
        "id",
        "request_id",
        "actor_id",
        "action",
        "target_type",
        "target_id",
        "outcome",
        "safe_metadata",
        "created_at",
    }
    assert item["safe_metadata"]["path"] == "/oauth/callback"
    assert item["safe_metadata"]["url"] == "https://agentos.example/tasks/42"
    assert ordinary in item["safe_metadata"]["detail"]
    assert set(item["safe_metadata"]) == {"detail", "path", "url"}
    serialized = response.text
    for unsafe in (*unsafe_values.values(), "top-secret", "session-secret", "totp-secret"):
        assert unsafe not in serialized
    assert serialized.count("[REDACTED]") >= len(unsafe_values)

    async with database.session_factory() as db:
        access_events = (
            await db.scalars(select(AuditEvent).where(AuditEvent.action == "audit.events.viewed"))
        ).all()
        assert len(access_events) == 1
        assert access_events[0].actor_id == admin.id
        assert access_events[0].outcome == "success"
        assert access_events[0].safe_metadata == {}
        assert str(access_events[0].id) not in {event["id"] for event in body["items"]}


@pytest.mark.asyncio
async def test_cursor_is_stable_for_equal_timestamps_and_new_inserts(audit_context) -> None:
    api, database, admin = audit_context
    created_at = datetime(2030, 1, 1, 12, tzinfo=UTC)
    seeded_ids = [UUID(int=index) for index in range(1, PAGE_SIZE * 2 + 2)]
    async with database.session_factory() as db:
        await db.execute(delete(AuditEvent))
        db.add_all(
            AuditEvent(
                id=event_id,
                request_id=f"request-{event_id.int}",
                actor_id=admin.id,
                action="task.executed",
                target_type="task",
                target_id=str(event_id.int),
                outcome="success" if event_id.int % 2 else "failure",
                safe_metadata={},
                created_at=created_at,
            )
            for event_id in seeded_ids
        )
        await db.commit()

    authenticated(api)
    first = await api.get("/audit/events", params={"action": "task.executed"})
    assert first.status_code == 200
    first_body = first.json()
    assert [UUID(item["id"]) for item in first_body["items"]] == list(
        reversed(seeded_ids[-PAGE_SIZE:])
    )
    assert isinstance(first_body["next_cursor"], str)

    async with database.session_factory() as db:
        db.add(
            AuditEvent(
                id=UUID(int=PAGE_SIZE * 2 + 2),
                request_id="request-new",
                actor_id=admin.id,
                action="task.executed",
                target_type="task",
                target_id="new",
                outcome="success",
                safe_metadata={},
                created_at=created_at + timedelta(seconds=1),
            )
        )
        await db.commit()

    second = await api.get(
        "/audit/events",
        params={"action": "task.executed", "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert [UUID(item["id"]) for item in second_body["items"]] == list(
        reversed(seeded_ids[1 : PAGE_SIZE + 1])
    )
    assert not (
        {item["id"] for item in first_body["items"]}
        & {item["id"] for item in second_body["items"]}
    )

    third = await api.get(
        "/audit/events",
        params={"action": "task.executed", "cursor": second_body["next_cursor"]},
    )
    assert third.status_code == 200
    assert [UUID(item["id"]) for item in third.json()["items"]] == [seeded_ids[0]]
    assert third.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_filters_use_the_exact_supported_outcome_enum(audit_context) -> None:
    api, database, admin = audit_context
    async with database.session_factory() as db:
        await db.execute(delete(AuditEvent))
        db.add_all(
            AuditEvent(
                request_id=f"request-{outcome}",
                actor_id=admin.id,
                action="task.executed" if outcome != "denied" else "task.created",
                outcome=outcome,
                safe_metadata={},
            )
            for outcome in ("success", "failure", "denied", "error", "rate_limited")
        )
        await db.commit()

    authenticated(api)
    for outcome in ("success", "failure", "denied", "error", "rate_limited"):
        response = await api.get(
            "/audit/events", params={"action": "task.executed", "outcome": outcome}
        )
        assert response.status_code == 200
        assert {item["outcome"] for item in response.json()["items"]} <= {outcome}
        assert {item["action"] for item in response.json()["items"]} <= {"task.executed"}

    for params in (
        {"outcome": ""},
        {"cursor": ""},
        {"cursor": "not-a-valid-cursor"},
    ):
        response = await api.get("/audit/events", params=params)
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
