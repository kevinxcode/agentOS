"""FastAPI application factory and dependency lifecycle."""

import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from typing import Protocol, cast
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
import structlog
from anyio import to_thread
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agentos.api.routes.audit import router as audit_router
from agentos.api.routes.auth import router as auth_router
from agentos.api.routes.health import ReadinessCheck
from agentos.api.routes.health import router as health_router
from agentos.config import Settings, get_settings
from agentos.db import create_database


class MinioClient(Protocol):
    def head_bucket(self, *, Bucket: str) -> object: ...

    def close(self) -> None: ...


logger = structlog.get_logger(__name__)


async def _check_postgresql(engine: AsyncEngine) -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True


async def _check_redis(client: Redis) -> bool:
    return bool(await client.ping())


async def _check_minio(client: MinioClient, bucket: str) -> bool:
    await to_thread.run_sync(
        partial(client.head_bucket, Bucket=bucket), abandon_on_cancel=True
    )
    return True


def _default_checks(
    engine: AsyncEngine,
    redis_client: Redis,
    minio_client: MinioClient,
    bucket: str,
) -> Mapping[str, ReadinessCheck]:
    return {
        "postgresql": partial(_check_postgresql, engine),
        "redis": partial(_check_redis, redis_client),
        "minio": partial(_check_minio, minio_client, bucket),
    }


def create_app(
    *,
    settings: Settings | None = None,
    readiness_checks: Mapping[str, ReadinessCheck] | None = None,
) -> FastAPI:
    """Build an API application with resources scoped to its ASGI lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or get_settings()
        app.state.settings = runtime_settings
        app.state.readiness_timeout_seconds = runtime_settings.readiness_timeout_seconds
        if readiness_checks is not None:
            app.state.readiness_checks = dict(readiness_checks)
            yield
            return

        async with AsyncExitStack() as resource_stack:
            database = create_database(runtime_settings.database_url)
            resource_stack.push_async_callback(database.close)
            redis_client = Redis.from_url(runtime_settings.redis_url, decode_responses=True)
            resource_stack.push_async_callback(redis_client.aclose)
            minio_client = cast(
                MinioClient,
                boto3.client(
                    "s3",
                    endpoint_url=runtime_settings.minio_endpoint,
                    aws_access_key_id=runtime_settings.minio_access_key,
                    aws_secret_access_key=runtime_settings.minio_secret_key,
                ),
            )
            resource_stack.callback(minio_client.close)
            app.state.database = database
            app.state.session_factory = database.session_factory
            app.state.readiness_checks = _default_checks(
                database.engine, redis_client, minio_client, runtime_settings.minio_bucket
            )
            yield

    app = FastAPI(title="AgentOS", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic's default errors may echo secret-valued input or a whole submitted body.
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @app.middleware("http")
    async def access_log(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = time.perf_counter()
        status_code = 500
        error_type: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            if request.url.path.startswith(("/auth/", "/audit/")):
                response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as error:
            error_type = type(error).__name__
            response = JSONResponse(
                content={"detail": "Internal Server Error"},
                status_code=status_code,
                headers={"X-Request-ID": request_id},
            )
            if request.url.path.startswith(("/auth/", "/audit/")):
                response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            logger.info(
                "http_request",
                duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
                method=request.method,
                path=request.url.path,
                request_id=request_id,
                status_code=status_code,
                error_type=error_type,
            )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(audit_router)
    return app
