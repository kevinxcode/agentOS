"""Alembic environment for async PostgreSQL and injected test connections."""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import agentos.auth.models  # noqa: F401  # Populate shared migration metadata.
from agentos.db import Base
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Resolve the migration URL without placing credentials in configuration files."""

    url = os.environ.get("AGENTOS_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("AGENTOS_DATABASE_URL is required to run migrations")
    return url


def run_migrations_offline() -> None:
    """Emit migration SQL without creating an Engine."""

    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def configure_and_run(connection: Connection) -> None:
    """Run migrations on a synchronous connection."""

    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Connect through the configured async driver and run sync Alembic operations."""

    engine = create_async_engine(database_url(), poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure_and_run)
    finally:
        await engine.dispose()


def run_sync_migrations(url: str) -> None:
    """Run migrations through a synchronous driver for local schema tests."""

    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            configure_and_run(connection)
    finally:
        engine.dispose()


def run_migrations_online() -> None:
    """Run against an injected test connection or the configured async database."""

    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        configure_and_run(supplied_connection)
        return
    url = database_url()
    if make_url(url).get_dialect().is_async:
        asyncio.run(run_async_migrations())
    else:
        run_sync_migrations(url)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
