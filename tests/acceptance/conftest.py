"""Disposable migrated database, never a production connection by default."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from agentos.api.app import create_app
from agentos.auth.models import AdminUser
from agentos.auth.service import BootstrapError, bootstrap_admin
from agentos.config import Settings
from agentos.db import create_database

ROOT = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture
async def foundation_stack(tmp_path):
    url = os.getenv(
        "AGENTOS_TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'gate.db'}"
    )
    if not url.startswith("sqlite") and make_url(url).database != "agentos_test":
        raise RuntimeError(
            "Service gate requires an explicitly disposable agentos_test database"
        )
    migration_url = url.replace("sqlite+aiosqlite", "sqlite")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "services/api/alembic.ini",
            "upgrade",
            "head",
        ],
        cwd=ROOT,
        env={**os.environ, "AGENTOS_DATABASE_URL": migration_url},
        check=True,
    )
    database = create_database(url)
    settings = Settings(
        environment="test",
        database_url="postgresql+asyncpg://u:p@db/test",
        redis_url="redis://redis:6379/0",
        minio_endpoint="http://minio:9000",
        minio_access_key="test",
        minio_secret_key="test",
        minio_bucket="agentos",
        session_pepper="p" * 32,
        master_key=Fernet.generate_key().decode(),
    )
    async with database.session_factory() as db:
        assert await db.scalar(select(AdminUser)) is None, (
            "Requires a fresh acceptance database"
        )
        assert await bootstrap_admin(db, "admin@example.com", "acceptance-password")
        assert not await bootstrap_admin(db, "admin@example.com", None)
        with pytest.raises(BootstrapError):
            await bootstrap_admin(db, "second@example.com", "another-password")
        admin = (await db.scalars(select(AdminUser))).one()
        if not url.startswith("sqlite"):
            assert admin.created_at.tzinfo is not None
        db.add(AdminUser(email="other@example.com", password_hash="not-a-real-hash"))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
        else:
            raise AssertionError("Database allowed a second administrator")
    app = create_app(settings=settings, readiness_checks={})
    try:
        async with app.router.lifespan_context(app):
            app.state.session_factory = database.session_factory
            yield app, database
    finally:
        await database.close()
