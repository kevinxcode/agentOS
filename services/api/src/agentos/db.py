"""Async database construction and lifecycle helpers."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative metadata for application persistence."""


@dataclass(frozen=True, slots=True)
class Database:
    """Application-scoped async engine and session factory."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def close(self) -> None:
        """Release connections owned by this application database."""

        await self.engine.dispose()


def create_database(database_url: str) -> Database:
    """Construct an isolated database lifecycle without opening a connection."""

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return Database(engine=engine, session_factory=session_factory)
