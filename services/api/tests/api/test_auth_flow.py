"""Real-database HTTP tests for privilege boundaries and one-time credentials."""

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update

from agentos.api.app import create_app
from agentos.auth import service as service_module
from agentos.auth.models import (
    AdminUser,
    AuditEvent,
    AuthRateLimit,
    RecoveryCode,
    Session,
    TotpEnrollment,
)
from agentos.config import Settings
from agentos.crypto import SecretCipher, hash_password, hash_token
from agentos.db import Base, create_database

PASSWORD = "valid-password"


@pytest_asyncio.fixture
async def context(tmp_path, monkeypatch) -> AsyncIterator[tuple]:
    # Keep real TOTP cryptography while making all time-window boundaries deterministic.
    frozen_now = datetime(2030, 1, 1, 12, 0, 15, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz is not None else frozen_now.replace(tzinfo=None)

    monkeypatch.setattr(service_module, "datetime", FrozenDatetime)
    monkeypatch.setattr(sys.modules[__name__], "datetime", FrozenDatetime)
    monkeypatch.setattr(pyotp.TOTP, "now", lambda self: self.at(frozen_now))
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
        auth_proxy_secret="s" * 32,
        cookie_secure=True,
    )
    database = create_database(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.session_factory() as db:
        admin = AdminUser(email="admin@example.com", password_hash=hash_password(PASSWORD))
        db.add(admin)
        await db.commit()
    app = create_app(settings=settings, readiness_checks={})
    async with app.router.lifespan_context(app):
        app.state.session_factory = database.session_factory
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as api:
            yield api, database, settings, admin
    await database.close()


async def login(api):
    return await api.post("/auth/login", json={"email": "admin@example.com", "password": PASSWORD})


async def seed(database, settings) -> str:
    # Secret access stays in the test's database dependency, never an HTTP-only test field.
    async with database.session_factory() as db:
        enrollment = (await db.scalars(select(TotpEnrollment))).one()
        return (
            SecretCipher(settings.master_key).decrypt_secret(enrollment.encrypted_secret).decode()
        )


async def enroll(context):
    api, database, settings, _ = context
    assert (await login(api)).status_code == 200
    assert (await api.post("/auth/totp/enroll")).status_code == 200
    secret = await seed(database, settings)
    response = await api.post("/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 200, response.text
    return secret, response.json()["recovery_codes"]


@pytest.mark.asyncio
async def test_admin_must_complete_totp_before_authenticated(context) -> None:
    api, database, settings, _ = context
    response = await login(api)
    assert response.status_code == 200
    assert response.json() == {"next": "totp_enrollment"}
    preauth = api.cookies.get("agentos_session")
    assert len(preauth) == 43  # URL-safe encoding of exactly 32 random bytes.
    assert (await api.get("/auth/me")).status_code == 401
    enrollment = await api.post("/auth/totp/enroll")
    assert enrollment.status_code == 200
    assert set(enrollment.json()) == {"otpauth_uri"}
    assert enrollment.json()["otpauth_uri"].startswith("otpauth://totp/AgentOS:")
    secret = await seed(database, settings)
    confirmed = await api.post("/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    assert confirmed.status_code == 200
    assert len(set(confirmed.json()["recovery_codes"])) == 10
    full = api.cookies.get("agentos_session")
    assert full != preauth
    cookie = confirmed.headers["set-cookie"]
    for value in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=43200"):
        assert value in cookie
    me = await api.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["totp_enabled"] is True
    assert set(me.json()) == {"id", "email", "totp_enabled"}
    assert "test_secret" not in confirmed.text + enrollment.text + me.text
    assert secret not in confirmed.text + me.text
    async with database.session_factory() as db:
        sessions = (await db.scalars(select(Session))).all()
        assert len(sessions) == 2
        assert {s.token_hash for s in sessions} == {
            hash_token(preauth, settings.session_pepper),
            hash_token(full, settings.session_pepper),
        }
        old = next(
            s for s in sessions if s.token_hash == hash_token(preauth, settings.session_pepper)
        )
        assert old.revoked_at is not None
        assert (old.expires_at - old.created_at).total_seconds() == 300
        codes = (await db.scalars(select(RecoveryCode))).all()
        assert len(codes) == 10
        assert all(c.code_hash.startswith("$argon2id$") for c in codes)
    assert (
        await api.get("/auth/me", headers={"Cookie": f"agentos_session={preauth}"})
    ).status_code == 401
    assert (
        await api.post("/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    ).status_code == 401


@pytest.mark.asyncio
async def test_wrong_password_unknown_user_and_rate_limit_are_generic(context) -> None:
    api, database, _, _ = context
    responses = []
    for index in range(6):
        responses.append(
            await api.post(
                "/auth/login",
                json={
                    "email": "admin@example.com" if index % 2 else "unknown@example.com",
                    "password": "wrong-secret-password",
                },
            )
        )
    assert [r.status_code for r in responses] == [401] * 5 + [429]
    assert responses[0].json() == responses[1].json()
    assert responses[-1].headers["retry-after"] == "60"
    assert not api.cookies
    async with database.session_factory() as db:
        events = (await db.scalars(select(AuditEvent))).all()
        assert len(events) == 6
        assert all(e.safe_metadata == {} for e in events)
        assert {e.outcome for e in events} == {"denied", "rate_limited"}


@pytest.mark.asyncio
async def test_login_normalizes_valid_email_and_rejects_browser_invalid_email(context) -> None:
    api, database, _, _ = context
    normalized = await api.post(
        "/auth/login", json={"email": "ADMIN@EXAMPLE.COM", "password": PASSWORD}
    )
    assert normalized.status_code == 200

    for email in ("admin name@example.com", " admin@example.com", "admin@example..com"):
        response = await api.post(
            "/auth/login", json={"email": email, "password": "secret-sentinel"}
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid request"}
        assert "secret-sentinel" not in response.text

    async with database.session_factory() as db:
        assert len((await db.scalars(select(AuthRateLimit))).all()) == 2


@pytest.mark.asyncio
async def test_totp_invalid_replayed_and_later_counter(context) -> None:
    api, database, _, _ = context
    secret, _ = await enroll(context)
    assert (await api.post("/auth/logout")).status_code == 204
    assert (await login(api)).json() == {"next": "totp_verification"}
    assert (await api.post("/auth/totp/enroll")).status_code == 409
    assert (await api.post("/auth/totp/verify", json={"code": "000000"})).status_code == 401
    assert (
        await api.post("/auth/totp/verify", json={"code": pyotp.TOTP(secret).now()})
    ).status_code == 401
    code = pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
    assert (await api.post("/auth/totp/verify", json={"code": code})).status_code == 200
    assert (await api.get("/auth/me")).status_code == 200
    async with database.session_factory() as db:
        events = (await db.scalars(select(AuditEvent))).all()
        assert "auth.totp.enrolled" in {e.action for e in events}
        assert all(e.safe_metadata == {} for e in events)
        assert secret not in repr([(e.action, e.safe_metadata) for e in events])


@pytest.mark.asyncio
async def test_recovery_code_is_one_time_and_cannot_bypass_password(context) -> None:
    api, _, _, _ = context
    _, codes = await enroll(context)
    await api.post("/auth/logout")
    assert (await api.post("/auth/recovery", json={"code": codes[0]})).status_code == 401
    await login(api)
    recovered = await api.post("/auth/recovery", json={"code": codes[0]})
    assert recovered.status_code == 200
    assert "recovery_codes" not in recovered.json()
    await api.post("/auth/logout")
    await login(api)
    assert (await api.post("/auth/recovery", json={"code": codes[0]})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["preauth", "absolute", "idle", "revoked", "inactive"])
async def test_expired_revoked_or_inactive_sessions_are_rejected(context, kind) -> None:
    api, database, settings, admin = context
    if kind == "preauth":
        await login(api)
    else:
        await enroll(context)
    token_hash = hash_token(api.cookies.get("agentos_session"), settings.session_pepper)
    async with database.session_factory() as db:
        session = (await db.scalars(select(Session).where(Session.token_hash == token_hash))).one()
        if kind in {"preauth", "absolute"}:
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif kind == "idle":
            session.last_seen_at = datetime.now(UTC) - timedelta(minutes=31)
        elif kind == "revoked":
            session.revoked_at = datetime.now(UTC)
        else:
            (await db.get(AdminUser, admin.id)).is_active = False
        await db.commit()
    path = "/auth/totp/enroll" if kind == "preauth" else "/auth/me"
    response = await (api.post(path) if kind == "preauth" else api.get(path))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_before_clearing_cookie(context) -> None:
    api, database, settings, admin = context
    await enroll(context)
    token = api.cookies.get("agentos_session")
    response = await api.post("/auth/logout")
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert not api.cookies
    async with database.session_factory() as db:
        session = (
            await db.scalars(
                select(Session).where(
                    Session.token_hash == hash_token(token, settings.session_pepper)
                )
            )
        ).one()
        assert session.revoked_at is not None
        logout_events = (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "auth.logout",
                    AuditEvent.outcome == "success",
                )
            )
        ).all()
        assert logout_events[-1].actor_id == admin.id
    assert (await api.post("/auth/logout")).status_code == 204
    async with database.session_factory() as db:
        logout_events = (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "auth.logout",
                    AuditEvent.outcome == "success",
                )
            )
        ).all()
        assert len(logout_events) == 2
        assert sum(event.actor_id == admin.id for event in logout_events) == 1
        assert sum(event.actor_id is None for event in logout_events) == 1
    assert (
        await api.get("/auth/me", headers={"Cookie": f"agentos_session={token}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_second_factor_attempts_are_rate_limited(context) -> None:
    api, _, _, _ = context
    await login(api)
    await api.post("/auth/totp/enroll")
    responses = [await api.post("/auth/totp/confirm", json={"code": "bad"}) for _ in range(6)]
    assert [r.status_code for r in responses] == [401] * 5 + [429]


@pytest.mark.asyncio
async def test_anonymous_mfa_attempts_from_one_ip_do_not_lock_out_another_ip(context) -> None:
    api, _, _, _ = context
    secret, _ = await enroll(context)
    await api.post("/auth/logout")
    assert (await login(api)).status_code == 200
    app = api._transport.app
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("198.51.100.10", 1000)),
        base_url="https://test",
    ) as attacker:
        responses = [
            await attacker.post("/auth/totp/verify", json={"code": "bad"}) for _ in range(6)
        ]
    assert [response.status_code for response in responses] == [401] * 5 + [429]
    assert (
        await api.post(
            "/auth/totp/verify",
            json={"code": pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_authenticated_mfa_account_budget_is_shared_across_ips(context) -> None:
    api, _, _, _ = context
    secret, _ = await enroll(context)
    await api.post("/auth/logout")
    assert (await login(api)).status_code == 200
    token = api.cookies.get("agentos_session")
    app = api._transport.app
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("198.51.100.13", 1003)),
        base_url="https://test",
    ) as attacker:
        responses = [
            await attacker.post(
                "/auth/totp/verify",
                headers={"Cookie": f"agentos_session={token}"},
                json={"code": "bad"},
            )
            for _ in range(4)
        ]
    assert [response.status_code for response in responses] == [401] * 4
    assert (
        await api.post(
            "/auth/totp/verify",
            json={"code": pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))},
        )
    ).status_code == 429


@pytest.mark.asyncio
async def test_login_limits_are_scoped_to_ip_and_normalized_identity(context) -> None:
    api, _, _, _ = context
    app = api._transport.app
    async with (
        AsyncClient(
            transport=ASGITransport(app=app, client=("198.51.100.11", 1001)),
            base_url="https://test",
        ) as client_a,
        AsyncClient(
            transport=ASGITransport(app=app, client=("198.51.100.12", 1002)),
            base_url="https://test",
        ) as client_b,
    ):
        for _ in range(5):
            assert (
                await client_a.post(
                    "/auth/login",
                    json={"email": "ADMIN@example.com", "password": "wrong-password"},
                )
            ).status_code == 401
        assert (
            await client_a.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": "wrong-password"},
            )
        ).status_code == 429
        assert (
            await client_a.post(
                "/auth/login",
                json={"email": "other@example.com", "password": "wrong-password"},
            )
        ).status_code == 429
        assert (
            await client_b.post(
                "/auth/login",
                json={"email": "admin@example.com", "password": PASSWORD},
            )
        ).status_code == 200


@pytest.mark.asyncio
async def test_trusted_proxy_identity_is_scoped_and_untrusted_headers_cannot_spoof(context) -> None:
    api, _, settings, _ = context
    app = api._transport.app
    trusted = {"x-agentos-proxy-secret": settings.auth_proxy_secret}
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("172.18.0.4", 1000)),
        base_url="https://test",
    ) as proxy:
        for _ in range(5):
            response = await proxy.post(
                "/auth/login",
                headers={**trusted, "x-agentos-client-ip": "198.51.100.10"},
                json={"email": "admin@example.com", "password": "wrong"},
            )
            assert response.status_code == 401
        assert (
            await proxy.post(
                "/auth/login",
                headers={**trusted, "x-agentos-client-ip": "198.51.100.10"},
                json={"email": "other@example.com", "password": "wrong"},
            )
        ).status_code == 429
        assert (
            await proxy.post(
                "/auth/login",
                headers={**trusted, "x-agentos-client-ip": "198.51.100.11"},
                json={"email": "admin@example.com", "password": PASSWORD},
            )
        ).status_code == 200

        for index in range(6):
            response = await proxy.post(
                "/auth/login",
                headers={
                    "x-agentos-proxy-secret": "x" * 32,
                    "x-agentos-client-ip": f"203.0.113.{index + 1}",
                },
                json={"email": f"spoof-{index}@example.com", "password": "wrong"},
            )
            assert response.status_code == (401 if index < 5 else 429)


@pytest.mark.asyncio
async def test_rejected_high_cardinality_logins_cannot_grow_rate_limit_rows(context) -> None:
    api, database, _, _ = context

    responses = [
        await api.post(
            "/auth/login",
            json={"email": f"unknown-{index}@example.com", "password": "wrong"},
        )
        for index in range(40)
    ]
    assert [response.status_code for response in responses[:6]] == [401] * 5 + [429]
    assert all(response.status_code == 429 for response in responses[5:])

    async with database.session_factory() as db:
        rows = (await db.scalars(select(AuthRateLimit))).all()
        assert len(rows) == 6  # one source budget and at most five identity budgets
        await db.execute(
            update(AuthRateLimit).values(
                window_started_at=int(datetime.now(UTC).timestamp()) - 61
            )
        )
        await db.commit()

    assert (
        await api.post(
            "/auth/login",
            json={"email": "fresh@example.com", "password": "wrong"},
        )
    ).status_code == 401
    async with database.session_factory() as db:
        assert len((await db.scalars(select(AuthRateLimit))).all()) == 2


@pytest.mark.asyncio
async def test_validation_does_not_echo_submitted_secrets(context) -> None:
    api, _, _, _ = context
    response = await api.post("/auth/login", json={"email": {}, "password": "secret-sentinel"})
    assert response.status_code == 422
    assert "secret-sentinel" not in response.text


@pytest.mark.asyncio
async def test_concurrent_confirmation_returns_recovery_codes_once(context) -> None:
    api, database, settings, _ = context
    await login(api)
    await api.post("/auth/totp/enroll")
    secret = await seed(database, settings)
    token = api.cookies.get("agentos_session")
    responses = await asyncio.gather(*[
        api.post("/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()},
                 headers={"Cookie": f"agentos_session={token}"})
        for _ in range(2)
    ])
    assert sorted(r.status_code for r in responses) == [200, 401]
    assert sum("recovery_codes" in r.json() for r in responses) == 1
    async with database.session_factory() as db:
        assert len((await db.scalars(select(RecoveryCode))).all()) == 10
        assert len((await db.scalars(select(Session).where(Session.stage == "full"))).all()) == 1


@pytest.mark.asyncio
async def test_concurrent_recovery_consumes_one_code_once(context) -> None:
    api, database, _, _ = context
    _, codes = await enroll(context)
    await api.post("/auth/logout")
    await login(api)
    token = api.cookies.get("agentos_session")
    responses = await asyncio.gather(*[
        api.post("/auth/recovery", json={"code": codes[0]},
                 headers={"Cookie": f"agentos_session={token}"})
        for _ in range(2)
    ])
    assert sorted(r.status_code for r in responses) == [200, 401]
    async with database.session_factory() as db:
        assert len((await db.scalars(select(RecoveryCode).where(
            RecoveryCode.used_at.is_not(None)
        ))).all()) == 1


@pytest.mark.asyncio
async def test_failed_elevation_rolls_back_seed_confirmation_and_codes(context) -> None:
    api, database, settings, _ = context
    await login(api)
    await api.post("/auth/totp/enroll")
    secret = await seed(database, settings)
    token = api.cookies.get("agentos_session")
    async with database.engine.begin() as connection:
        await connection.execute(text(
            "CREATE TRIGGER fail_full_session BEFORE INSERT ON sessions "
            "WHEN NEW.stage = 'full' BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END"
        ))
    response = await api.post("/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    assert response.status_code == 500
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert api.cookies.get("agentos_session") == token
    async with database.session_factory() as db:
        enrollment = (await db.scalars(select(TotpEnrollment))).one()
        assert enrollment.confirmed_at is None
        assert enrollment.last_used_counter is None
        assert not (await db.scalars(select(RecoveryCode))).all()
        assert (await db.scalars(select(Session))).one().revoked_at is None
        error_events = (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "auth.totp.enrolled",
                    AuditEvent.outcome == "error",
                )
            )
        ).all()
        assert len(error_events) == 1
        assert error_events[0].safe_metadata == {}
    async with database.engine.begin() as connection:
        await connection.execute(text("DROP TRIGGER fail_full_session"))
    assert (
        await api.post("/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    ).status_code == 200


@pytest.mark.asyncio
async def test_unexpected_error_audit_outage_logs_only_redacted_types(
    context, monkeypatch, capsys
) -> None:
    api, _, _, _ = context

    async def broken_me(self):
        raise RuntimeError("operation-secret-sentinel")

    def broken_audit(*args, **kwargs):
        raise RuntimeError("audit-secret-sentinel")

    monkeypatch.setattr(service_module.AuthService, "me", broken_me)
    monkeypatch.setattr(service_module, "record_event", broken_audit)
    response = await api.get("/auth/me")
    assert response.status_code == 500
    captured = capsys.readouterr()
    logs = captured.out + captured.err
    assert "operation-secret-sentinel" not in logs
    assert "audit-secret-sentinel" not in logs


@pytest.mark.asyncio
async def test_rate_limit_resets_and_is_shared_across_app_instances(context) -> None:
    api, database, settings, _ = context
    for _ in range(5):
        await api.post("/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    app = create_app(settings=settings, readiness_checks={})
    async with app.router.lifespan_context(app):
        app.state.session_factory = database.session_factory
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as other:
            assert (await login(other)).status_code == 429
    async with database.session_factory() as db:
        await db.execute(update(AuthRateLimit).values(
            window_started_at=int(datetime.now(UTC).timestamp()) - 61
        ))
        await db.commit()
    assert (await login(api)).status_code == 200


@pytest.mark.asyncio
async def test_all_secret_material_is_absent_from_logs_and_audit(context, capsys) -> None:
    api, database, _, _ = context
    secret, codes = await enroll(context)
    token = api.cookies.get("agentos_session")
    await api.post("/auth/logout")
    logs = capsys.readouterr().out
    async with database.session_factory() as db:
        events = (await db.scalars(select(AuditEvent))).all()
        audit = repr([(e.action, e.outcome, e.safe_metadata, e.target_id) for e in events])
    for sensitive in [PASSWORD, secret, token, *codes]:
        assert sensitive not in logs + audit
    assert {e.action for e in events} >= {"auth.login", "auth.totp.enrolled", "auth.logout"}


@pytest.mark.asyncio
async def test_auth_state_is_typed_read_only_and_never_refreshes_or_rate_limits(context) -> None:
    api, database, settings, _ = context
    anonymous = await api.get("/auth/state")
    assert anonymous.status_code == 200
    assert anonymous.json() == {"stage": "anonymous"}
    assert anonymous.headers["cache-control"] == "no-store"

    assert (await login(api)).status_code == 200
    token_hash = hash_token(api.cookies.get("agentos_session"), settings.session_pepper)
    async with database.session_factory() as db:
        before_session = (
            await db.scalars(select(Session).where(Session.token_hash == token_hash))
        ).one()
        before_last_seen = before_session.last_seen_at
        before_limits = [
            (row.key, row.attempts) for row in (await db.scalars(select(AuthRateLimit))).all()
        ]
        before_audits = len((await db.scalars(select(AuditEvent))).all())

    for _ in range(3):
        state = await api.get("/auth/state")
        assert state.status_code == 200
        assert state.json() == {"stage": "preauth", "next": "totp_enrollment"}
        assert set(state.json()) == {"stage", "next"}

    async with database.session_factory() as db:
        after_session = (
            await db.scalars(select(Session).where(Session.token_hash == token_hash))
        ).one()
        assert after_session.last_seen_at == before_last_seen
        assert [
            (row.key, row.attempts) for row in (await db.scalars(select(AuthRateLimit))).all()
        ] == before_limits
        assert len((await db.scalars(select(AuditEvent))).all()) == before_audits

    secret, _ = await enroll(context)
    full = await api.get("/auth/state")
    assert full.status_code == 200
    assert full.json() == {
        "stage": "full",
        "id": str((await api.get("/auth/me")).json()["id"]),
        "email": "admin@example.com",
        "totp_enabled": True,
    }
    assert secret not in full.text


@pytest.mark.asyncio
async def test_enrollment_retry_preserves_seed_and_access_does_not_extend_absolute_expiry(
    context,
) -> None:
    api, database, settings, _ = context
    await login(api)
    first = await api.post("/auth/totp/enroll")
    second = await api.post("/auth/totp/enroll")
    assert first.json() == second.json()
    secret = await seed(database, settings)
    await api.post("/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    token_hash = hash_token(api.cookies.get("agentos_session"), settings.session_pepper)
    async with database.session_factory() as db:
        session = (await db.scalars(select(Session).where(Session.token_hash == token_hash))).one()
        deadline = session.expires_at
        previous = datetime.now(UTC) - timedelta(minutes=10)
        session.last_seen_at = previous
        await db.commit()
    assert (await api.get("/auth/me")).status_code == 200
    async with database.session_factory() as db:
        session = (await db.scalars(select(Session).where(Session.token_hash == token_hash))).one()
        assert session.expires_at == deadline
        assert session.last_seen_at.replace(tzinfo=UTC) > previous
