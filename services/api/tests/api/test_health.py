import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from agentos.api import app as app_module
from agentos.api.app import create_app
from agentos.api.routes.health import ReadinessResponse
from agentos.config import Settings

ReadinessCheck = Callable[[], Awaitable[bool]]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql+asyncpg://u:database-password@db/app",
        redis_url="redis://:redis-password@redis:6379/0",
        minio_endpoint="http://minio:9000",
        minio_access_key="minio-access-key",
        minio_secret_key="minio-secret-key",
        minio_bucket="agentos",
        session_pepper="session-pepper-value-that-is-long",
        master_key=Fernet.generate_key().decode("ascii"),
    )


@pytest.fixture
def broken_checks() -> Mapping[str, ReadinessCheck]:
    async def healthy() -> bool:
        return True

    async def broken() -> bool:
        raise ConnectionError("contains-sensitive-connection-detail")

    return {"postgresql": healthy, "redis": broken, "minio": healthy}


@pytest_asyncio.fixture
async def client(
    settings: Settings, broken_checks: Mapping[str, ReadinessCheck]
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=settings, readiness_checks=broken_checks)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            yield test_client


@pytest.mark.asyncio
async def test_liveness_does_not_require_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_reports_dependency_failure(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unready",
        "dependencies": {"postgresql": "up", "redis": "down", "minio": "up"},
    }
    assert "contains-sensitive-connection-detail" not in response.text
    assert "password" not in response.text


@pytest.mark.asyncio
async def test_readiness_checks_dependencies_concurrently(settings: Settings) -> None:
    all_started = asyncio.Event()
    started = 0

    async def wait_for_peers() -> bool:
        nonlocal started
        started += 1
        if started == 3:
            all_started.set()
        await all_started.wait()
        return True

    checks = {name: wait_for_peers for name in ("postgresql", "redis", "minio")}
    app = create_app(settings=settings, readiness_checks=checks)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await asyncio.wait_for(test_client.get("/health/ready"), timeout=0.5)

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_readiness_times_out_a_non_returning_dependency(settings: Settings) -> None:
    cancelled = asyncio.Event()

    async def healthy() -> bool:
        return True

    async def never_returns() -> bool:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    checks = {"postgresql": healthy, "redis": never_returns, "minio": healthy}
    settings.readiness_timeout_seconds = 0.01
    app = create_app(settings=settings, readiness_checks=checks)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await asyncio.wait_for(test_client.get("/health/ready"), timeout=0.2)

    assert response.status_code == 503
    assert response.json()["dependencies"]["redis"] == "down"
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_response_has_generated_request_id(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "untrusted-id"})

    request_id = response.headers["X-Request-ID"]
    assert request_id != "untrusted-id"
    assert len(request_id) == 36


@pytest.mark.asyncio
async def test_downstream_exception_returns_request_id_and_logs_same_id(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(settings=settings, readiness_checks={})

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("sensitive backend detail")

    logger = MagicMock()
    monkeypatch.setattr(app_module, "logger", logger)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            response = await test_client.get("/boom")

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert "sensitive backend detail" not in response.text
    assert logger.info.call_args.kwargs["request_id"] == request_id
    assert logger.info.call_args.kwargs["status_code"] == 500
    assert logger.info.call_args.kwargs["error_type"] == "RuntimeError"


def test_health_routes_publish_typed_success_and_failure_schemas(
    settings: Settings,
) -> None:
    app = create_app(settings=settings, readiness_checks={})

    openapi = app.openapi()
    live_responses = openapi["paths"]["/health/live"]["get"]["responses"]
    ready_responses = openapi["paths"]["/health/ready"]["get"]["responses"]

    assert live_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/LivenessResponse"
    )
    assert ready_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ReadinessResponse"
    )
    assert ready_responses["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ReadinessResponse"
    )
    assert ReadinessResponse(
        status="unready", dependencies={"redis": "down"}
    ).model_dump() == {"status": "unready", "dependencies": {"redis": "down"}}

    with pytest.raises(ValueError):
        ReadinessResponse(status="unready", dependencies={"redis": "unknown"})


def patch_resources(
    monkeypatch: pytest.MonkeyPatch, *, redis_close_error: Exception | None = None
) -> tuple[MagicMock, MagicMock, MagicMock]:
    database = MagicMock()
    database.close = AsyncMock()
    redis_client = MagicMock()
    redis_client.aclose = AsyncMock(side_effect=redis_close_error)
    minio_client = MagicMock()

    monkeypatch.setattr(app_module, "create_database", MagicMock(return_value=database))
    monkeypatch.setattr(app_module.Redis, "from_url", MagicMock(return_value=redis_client))
    monkeypatch.setattr(app_module.boto3, "client", MagicMock(return_value=minio_client))
    return database, redis_client, minio_client


@pytest.mark.asyncio
async def test_lifespan_closes_database_redis_and_minio(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, redis_client, minio_client = patch_resources(monkeypatch)
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        assert app.state.session_factory is database.session_factory

    minio_client.close.assert_called_once_with()
    redis_client.aclose.assert_awaited_once_with()
    database.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_lifespan_continues_cleanup_after_redis_close_failure(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, redis_client, minio_client = patch_resources(
        monkeypatch, redis_close_error=RuntimeError("redis cleanup failed")
    )
    app = create_app(settings=settings)

    with pytest.raises(RuntimeError, match="redis cleanup failed"):
        async with app.router.lifespan_context(app):
            pass

    minio_client.close.assert_called_once_with()
    redis_client.aclose.assert_awaited_once_with()
    database.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_default_checks_call_concrete_clients(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=None)
    connection.execute = AsyncMock()
    engine = MagicMock()
    engine.connect.return_value = connection

    database = MagicMock(engine=engine, session_factory=object())
    database.close = AsyncMock()
    redis_client = MagicMock()
    redis_client.ping = AsyncMock(return_value=True)
    redis_client.aclose = AsyncMock()
    minio_client = MagicMock()

    monkeypatch.setattr(app_module, "create_database", MagicMock(return_value=database))
    monkeypatch.setattr(app_module.Redis, "from_url", MagicMock(return_value=redis_client))
    monkeypatch.setattr(app_module.boto3, "client", MagicMock(return_value=minio_client))
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        checks = app.state.readiness_checks
        assert await checks["postgresql"]()
        assert await checks["redis"]()
        assert await checks["minio"]()

    executed = connection.execute.await_args.args[0]
    assert str(executed) == "SELECT 1"
    redis_client.ping.assert_awaited_once_with()
    minio_client.head_bucket.assert_called_once_with(Bucket="agentos")
