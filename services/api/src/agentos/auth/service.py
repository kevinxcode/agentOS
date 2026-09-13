"""Transactional password/second-factor authentication with durable replay defense."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from anyio import to_thread
from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentos.audit.service import record_event
from agentos.auth.email import normalize_email
from agentos.auth.models import AdminUser, AuthRateLimit, RecoveryCode, Session, TotpEnrollment
from agentos.auth.totp import matching_counter, new_secret, provisioning_uri
from agentos.config import Settings
from agentos.crypto import (
    SecretCipher,
    hash_password,
    hash_recovery_code,
    hash_token,
    verify_password,
    verify_recovery_code,
)

PREAUTH_SECONDS = 300
FULL_SECONDS = 43200
IDLE_SECONDS = 1800
# A real Argon2id hash makes unknown-user verification follow the same expensive path.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class AuthError(Exception):
    def __init__(self, status: int = 401) -> None:
        self.status = status


class BootstrapError(Exception):
    """Safe operator-facing bootstrap failure."""


async def bootstrap_admin(db: AsyncSession, email: str, password: str | None) -> bool:
    """Idempotently create the sole administrator without replacing existing credentials."""
    try:
        email = normalize_email(email)
    except ValueError:
        raise BootstrapError("A valid administrator email is required") from None
    request_id = str(uuid4())
    existing = await db.scalar(select(AdminUser))
    if existing is not None:
        if existing.email == email:
            return False
        record_event(db, request_id=request_id, action="auth.bootstrap", outcome="denied")
        await db.commit()
        raise BootstrapError("A different administrator already exists")
    if password is None or not 12 <= len(password) <= 1024:
        raise BootstrapError("Password must contain 12 to 1024 characters")
    admin = AdminUser(email=email, password_hash=await to_thread.run_sync(hash_password, password))
    db.add(admin)
    try:
        await db.flush()
        record_event(
            db, request_id=request_id, action="auth.bootstrap", outcome="success", actor_id=admin.id
        )
        await db.commit()
    except IntegrityError:
        # The database singleton is the race arbiter, not the optimistic first query.
        await db.rollback()
        existing = await db.scalar(select(AdminUser))
        if existing is not None and existing.email == email:
            return False
        record_event(db, request_id=request_id, action="auth.bootstrap", outcome="denied")
        await db.commit()
        raise BootstrapError("An administrator already exists") from None
    return True


def utc(value: datetime) -> datetime:
    # SQLite drops timezone annotations; PostgreSQL stores timezone-aware timestamptz.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        *,
        request_id: str,
        ip: str,
        user_agent: str,
        token: str | None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.cipher = SecretCipher(settings.master_key)
        self.request_id = request_id
        self.ip_hash = hash_token("ip:" + ip, settings.session_pepper)
        self.user_agent_hash = hash_token("ua:" + user_agent, settings.session_pepper)
        self.token = token
        self.actor_id: UUID | None = None

    async def rate_limit(
        self,
        scope: str,
        *,
        identity: str | None = None,
        account_id: UUID | None = None,
        include_ip: bool = True,
    ) -> None:
        """Atomically enforce shared ingress, identity, and account budgets."""
        now = int(datetime.now(UTC).timestamp())
        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        await self.db.execute(
            delete(AuthRateLimit).where(AuthRateLimit.window_started_at <= now - 60)
        )
        if include_ip:
            source_key = hash_token(
                f"rate:{scope}:ip:{self.ip_hash}", self.settings.session_pepper
            )
            source_count = await self._increment_rate_limit(insert, source_key, now)
            await self.db.commit()
            if source_count > 5:
                raise AuthError(429)

        keys: list[str] = []
        if identity is not None:
            normalized = identity.strip().lower()
            identity_hash = hash_token(f"identity:{normalized}", self.settings.session_pepper)
            keys.append(
                hash_token(
                    f"rate:{scope}:identity-ip:{identity_hash}:{self.ip_hash}",
                    self.settings.session_pepper,
                )
            )
        if account_id is not None:
            keys.append(
                hash_token(f"rate:{scope}:account:{account_id}", self.settings.session_pepper)
            )
        counts: list[int] = []
        for key in keys:
            counts.append(await self._increment_rate_limit(insert, key, now))
        await self.db.commit()
        if counts and max(counts) > 5:
            raise AuthError(429)

    async def _increment_rate_limit(self, insert, key: str, now: int) -> int:
        expired = AuthRateLimit.window_started_at <= now - 60
        statement = insert(AuthRateLimit).values(key=key, window_started_at=now, attempts=1)
        returning = statement.on_conflict_do_update(
            index_elements=[AuthRateLimit.key],
            set_={
                "attempts": case((expired, 1), else_=AuthRateLimit.attempts + 1),
                "window_started_at": case(
                    (expired, now), else_=AuthRateLimit.window_started_at
                ),
            },
        ).returning(AuthRateLimit.attempts)
        return (await self.db.execute(returning)).scalar_one()

    async def current(self, stage: str | None = None) -> tuple[Session, AdminUser]:
        if not self.token or len(self.token) != 43:
            raise AuthError()
        now = datetime.now(UTC)
        session = await self.db.scalar(
            select(Session).where(
                Session.token_hash == hash_token(self.token, self.settings.session_pepper)
            )
        )
        if (
            session is None
            or session.revoked_at is not None
            or utc(session.expires_at) <= now
            or utc(session.last_seen_at) + timedelta(seconds=IDLE_SECONDS) <= now
            or (stage is not None and session.stage != stage)
        ):
            raise AuthError()
        admin = await self.db.get(AdminUser, session.admin_user_id)
        if admin is None or not admin.is_active:
            raise AuthError()
        self.actor_id = admin.id
        session.last_seen_at = now
        return session, admin

    async def state(self) -> dict[str, object]:
        """Inspect authentication stage without refreshing or otherwise mutating it."""
        if not self.token or len(self.token) != 43:
            return {"stage": "anonymous"}
        now = datetime.now(UTC)
        row = (
            await self.db.execute(
                select(Session, AdminUser)
                .join(AdminUser, AdminUser.id == Session.admin_user_id)
                .where(Session.token_hash == hash_token(self.token, self.settings.session_pepper))
            )
        ).one_or_none()
        if row is None:
            return {"stage": "anonymous"}
        session, admin = row
        if (
            session.revoked_at is not None
            or utc(session.expires_at) <= now
            or utc(session.last_seen_at) + timedelta(seconds=IDLE_SECONDS) <= now
            or not admin.is_active
        ):
            return {"stage": "anonymous"}
        if session.stage == "full":
            return {
                "stage": "full",
                "id": admin.id,
                "email": admin.email,
                "totp_enabled": True,
            }
        enrollment = await self.db.scalar(
            select(TotpEnrollment).where(TotpEnrollment.admin_user_id == admin.id)
        )
        return {
            "stage": "preauth",
            "next": (
                "totp_verification"
                if enrollment is not None and enrollment.confirmed_at is not None
                else "totp_enrollment"
            ),
        }

    async def issue(self, admin: AdminUser, stage: str) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self.db.add(
            Session(
                admin_user_id=admin.id,
                token_hash=hash_token(token, self.settings.session_pepper),
                stage=stage,
                expires_at=now
                + timedelta(seconds=PREAUTH_SECONDS if stage == "preauth" else FULL_SECONDS),
                created_at=now,
                last_seen_at=now,
                ip_hash=self.ip_hash,
                user_agent_hash=self.user_agent_hash,
            )
        )
        return token

    async def login(self, email: str, password: str) -> tuple[dict[str, object], str]:
        normalized_email = normalize_email(email)
        await self.rate_limit("login", identity=normalized_email)
        admin = await self.db.scalar(
            select(AdminUser).where(AdminUser.email == normalized_email)
        )
        valid = await to_thread.run_sync(
            verify_password, admin.password_hash if admin else _DUMMY_PASSWORD_HASH, password
        )
        if not valid or admin is None or not admin.is_active:
            raise AuthError()
        self.actor_id = admin.id
        # Re-login replaces the supplied browser session, including a previous full session.
        if self.token:
            await self.db.execute(
                update(Session)
                .where(
                    Session.token_hash == hash_token(self.token, self.settings.session_pepper),
                    Session.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )
        enrollment = await self.db.scalar(
            select(TotpEnrollment).where(TotpEnrollment.admin_user_id == admin.id)
        )
        next_step = (
            "totp_verification" if enrollment and enrollment.confirmed_at else "totp_enrollment"
        )
        return {"next": next_step}, await self.issue(admin, "preauth")

    async def enroll(self) -> dict[str, object]:
        await self.rate_limit("enroll")
        _, admin = await self.current("preauth")
        await self.rate_limit("enroll", account_id=admin.id, include_ip=False)
        # Conflict-safe insert keeps retries and concurrent preauth sessions on one seed.
        insert = sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        await self.db.execute(
            insert(TotpEnrollment)
            .values(
                id=uuid4(),
                admin_user_id=admin.id,
                encrypted_secret=self.cipher.encrypt_secret(new_secret().encode()),
            )
            .on_conflict_do_nothing(index_elements=[TotpEnrollment.admin_user_id])
        )
        enrollment = (
            await self.db.scalars(
                select(TotpEnrollment).where(TotpEnrollment.admin_user_id == admin.id)
            )
        ).one()
        if enrollment.confirmed_at is not None:
            raise AuthError(409)
        secret = self.cipher.decrypt_secret(enrollment.encrypted_secret).decode()
        return {"otpauth_uri": provisioning_uri(secret, admin.email)}

    async def elevate(self, session: Session, admin: AdminUser) -> str:
        now = datetime.now(UTC)
        consumed = (
            await self.db.execute(
                update(Session)
                .where(
                    Session.id == session.id,
                    Session.stage == "preauth",
                    Session.revoked_at.is_(None),
                    Session.expires_at > now,
                )
                .values(revoked_at=now)
                .returning(Session.id)
                .execution_options(synchronize_session="fetch")
            )
        ).scalar_one_or_none()
        if consumed is None:
            raise AuthError()
        return await self.issue(admin, "full")

    async def verify_totp(self, code: str, *, confirm: bool) -> tuple[dict[str, object], str]:
        await self.rate_limit("second-factor")
        session, admin = await self.current("preauth")
        await self.rate_limit("second-factor", account_id=admin.id, include_ip=False)
        enrollment = await self.db.scalar(
            select(TotpEnrollment).where(TotpEnrollment.admin_user_id == admin.id)
        )
        if enrollment is None or (enrollment.confirmed_at is None) != confirm:
            raise AuthError()
        now = datetime.now(UTC)
        secret = self.cipher.decrypt_secret(enrollment.encrypted_secret).decode()
        counter = matching_counter(secret, code, now)
        if counter is None:
            raise AuthError()
        statement = (
            update(TotpEnrollment)
            .where(
                TotpEnrollment.id == enrollment.id,
                or_(
                    TotpEnrollment.last_used_counter.is_(None),
                    TotpEnrollment.last_used_counter < counter,
                ),
                TotpEnrollment.confirmed_at.is_(None)
                if confirm
                else TotpEnrollment.confirmed_at.is_not(None),
            )
            .values(last_used_counter=counter)
        )
        if confirm:
            statement = statement.values(confirmed_at=now)
        consumed = (
            await self.db.execute(statement.returning(TotpEnrollment.id))
        ).scalar_one_or_none()
        if consumed is None:
            raise AuthError()
        result: dict[str, object] = {"authenticated": True}
        if confirm:
            codes = [secrets.token_urlsafe(16) for _ in range(10)]
            for code_value in codes:
                self.db.add(
                    RecoveryCode(
                        admin_user_id=admin.id,
                        code_hash=await to_thread.run_sync(hash_recovery_code, code_value),
                    )
                )
            result = {"recovery_codes": codes}
        return result, await self.elevate(session, admin)

    async def recover(self, code: str) -> tuple[dict[str, object], str]:
        await self.rate_limit("second-factor")
        session, admin = await self.current("preauth")
        await self.rate_limit("second-factor", account_id=admin.id, include_ip=False)
        enrollment = await self.db.scalar(
            select(TotpEnrollment).where(
                TotpEnrollment.admin_user_id == admin.id, TotpEnrollment.confirmed_at.is_not(None)
            )
        )
        if enrollment is None:
            raise AuthError()
        codes = (
            await self.db.scalars(
                select(RecoveryCode).where(
                    RecoveryCode.admin_user_id == admin.id, RecoveryCode.used_at.is_(None)
                )
            )
        ).all()
        matched = None
        for candidate in codes:
            if await to_thread.run_sync(verify_recovery_code, candidate.code_hash, code):
                matched = candidate
        if matched is None:
            raise AuthError()
        consumed = (
            await self.db.execute(
                update(RecoveryCode)
                .where(
                    RecoveryCode.id == matched.id,
                    RecoveryCode.used_at.is_(None),
                )
                .values(used_at=datetime.now(UTC))
                .returning(RecoveryCode.id)
            )
        ).scalar_one_or_none()
        if consumed is None:
            raise AuthError()
        return {"authenticated": True}, await self.elevate(session, admin)

    async def logout(self) -> UUID | None:
        # Idempotent even for expired cookies: revoke the matching record if it exists.
        if not self.token:
            return None
        admin_id = (
            await self.db.execute(
                update(Session)
                .where(
                    Session.token_hash == hash_token(self.token, self.settings.session_pepper),
                    Session.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
                .returning(Session.admin_user_id)
            )
        ).scalar_one_or_none()
        if admin_id is not None:
            self.actor_id = admin_id
        return admin_id

    async def me(self) -> dict[str, object]:
        _, admin = await self.current("full")
        return {"id": admin.id, "email": admin.email, "totp_enabled": True}

    def audit(self, action: str, outcome: str) -> None:
        record_event(
            self.db,
            request_id=self.request_id,
            actor_id=self.actor_id,
            action=action,
            outcome=outcome,
        )
