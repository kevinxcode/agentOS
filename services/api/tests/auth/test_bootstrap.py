"""Bootstrap creates one identity and never resets an existing administrator."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from agentos.auth.models import AdminUser, AuditEvent
from agentos.crypto import verify_password
from agentos.db import Base, create_database

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "bootstrap_admin.py"


def cli_module():
    spec = importlib.util.spec_from_file_location("bootstrap_admin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_and_rejects_second_identity(tmp_path) -> None:
    from agentos.auth.service import BootstrapError, bootstrap_admin

    database = create_database(f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.session_factory() as db:
        assert await bootstrap_admin(db, "ADMIN@example.com", "valid-password") is True
        admin = (await db.scalars(select(AdminUser))).one()
        original = admin.password_hash
        assert admin.email == "admin@example.com"
        assert verify_password(original, "valid-password")
        assert await bootstrap_admin(db, "admin@example.com", "different-password") is False
        assert admin.password_hash == original
        with pytest.raises(BootstrapError):
            await bootstrap_admin(db, "second@example.com", "valid-password")
        events = (await db.scalars(select(AuditEvent))).all()
        assert {e.action for e in events} == {"auth.bootstrap"}
        assert {e.outcome for e in events} == {"success", "denied"}
        assert all(e.safe_metadata == {} for e in events)
    await database.close()


def test_cli_rejects_password_argument() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--email", "admin@example.com", "--password", "sentinel"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert "sentinel" not in result.stdout + result.stderr


def test_cli_reads_password_file_or_interactive_prompt(tmp_path, monkeypatch) -> None:
    module = cli_module()
    path = tmp_path / "password"
    path.write_text("file-password\n")
    monkeypatch.setenv("AGENTOS_BOOTSTRAP_PASSWORD_FILE", str(path))
    assert module.read_password() == "file-password"
    monkeypatch.delenv("AGENTOS_BOOTSTRAP_PASSWORD_FILE")
    monkeypatch.setattr(module.getpass, "getpass", lambda prompt: "prompt-password")
    assert module.read_password() == "prompt-password"


def test_cli_rejects_overlong_password_file_instead_of_truncating(tmp_path, monkeypatch) -> None:
    module = cli_module()
    path = tmp_path / "password"
    path.write_text("a" * 1024 + "\n\ntrailing-material")
    monkeypatch.setenv("AGENTOS_BOOTSTRAP_PASSWORD_FILE", str(path))
    with pytest.raises(module.BootstrapError):
        module.read_password()


@pytest.mark.parametrize("password", ["", "short", "x" * 1025])
@pytest.mark.asyncio
async def test_bootstrap_rejects_weak_or_unusable_password(tmp_path, password) -> None:
    from agentos.auth.service import BootstrapError, bootstrap_admin

    database = create_database(f"sqlite+aiosqlite:///{tmp_path / 'invalid.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.session_factory() as db:
        with pytest.raises(BootstrapError):
            await bootstrap_admin(db, "admin@example.com", password)
        assert not (await db.scalars(select(AdminUser))).all()
    await database.close()


@pytest.mark.parametrize(
    "email",
    [
        "admin name@example.com",
        " admin@example.com",
        "admin@example.com ",
        "admin@-example.com",
        "admin@example..com",
        "admiñ@example.com",
    ],
)
@pytest.mark.asyncio
async def test_bootstrap_rejects_browser_invalid_email_before_singleton_insert(
    tmp_path, email
) -> None:
    from agentos.auth.service import BootstrapError, bootstrap_admin

    database = create_database(f"sqlite+aiosqlite:///{tmp_path / 'invalid-email.db'}")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.session_factory() as db:
        with pytest.raises(BootstrapError, match="valid administrator email"):
            await bootstrap_admin(db, email, "valid-password")
        assert not (await db.scalars(select(AdminUser))).all()
    await database.close()
