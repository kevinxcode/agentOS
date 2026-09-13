import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from agentos.auth.models import AdminUser
from agentos.db import Base
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = ROOT / "services" / "api" / "alembic.ini"
EXPECTED_TABLES = {
    "admin_users",
    "sessions",
    "totp_enrollments",
    "recovery_codes",
    "audit_events",
}
FORBIDDEN_PLAINTEXT_COLUMNS = {"password", "token", "totp_secret", "recovery_code"}


def migrated_engine(tmp_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return engine


def test_fresh_migration_creates_auth_and_audit_schema(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    schema = inspect(engine)

    assert EXPECTED_TABLES <= set(schema.get_table_names())
    for table in EXPECTED_TABLES:
        column_names = {column["name"] for column in schema.get_columns(table)}
        assert column_names.isdisjoint(FORBIDDEN_PLAINTEXT_COLUMNS)


def test_cli_upgrade_uses_environment_database_url(tmp_path: Path) -> None:
    database_path = tmp_path / "cli-auth.db"
    environment = os.environ.copy()
    environment["AGENTOS_DATABASE_URL"] = f"sqlite:///{database_path}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert EXPECTED_TABLES <= set(
        inspect(create_engine(f"sqlite:///{database_path}")).get_table_names()
    )


def test_migration_columns_match_the_persistence_contract(tmp_path: Path) -> None:
    schema = inspect(migrated_engine(tmp_path))

    assert {column["name"] for column in schema.get_columns("admin_users")} >= {
        "email",
        "password_hash",
    }
    assert {column["name"] for column in schema.get_columns("sessions")} >= {
        "token_hash",
        "expires_at",
        "revoked_at",
        "last_seen_at",
        "ip_hash",
        "user_agent_hash",
    }
    assert {column["name"] for column in schema.get_columns("totp_enrollments")} >= {
        "encrypted_secret",
    }
    assert {column["name"] for column in schema.get_columns("recovery_codes")} >= {
        "code_hash",
    }
    assert {column["name"] for column in schema.get_columns("audit_events")} >= {
        "request_id",
        "actor_id",
        "action",
        "target_type",
        "target_id",
        "outcome",
        "safe_metadata",
        "created_at",
    }
    assert "updated_at" not in {column["name"] for column in schema.get_columns("audit_events")}


def test_database_enforces_one_admin_user(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)

    with OrmSession(engine) as session:
        session.add(AdminUser(email="first@example.com", password_hash="argon-hash"))
        session.commit()
        session.add(AdminUser(email="second@example.com", password_hash="argon-hash"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_models_share_the_application_declarative_base() -> None:
    assert AdminUser.metadata is Base.metadata
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


@pytest.mark.parametrize("key", [0, 2, -1])
def test_raw_sql_cannot_bypass_singleton_check(tmp_path: Path, key: int) -> None:
    engine = migrated_engine(tmp_path)
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO admin_users (id, singleton_key, email, password_hash) "
                    "VALUES ('00000000000000000000000000000001', :key, 'a@b.test', 'hash')"
                ),
                {"key": key},
            )
