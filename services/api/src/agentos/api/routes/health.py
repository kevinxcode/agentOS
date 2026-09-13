"""Process liveness and dependency-aware readiness routes."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal, cast

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ReadinessCheck = Callable[[], Awaitable[bool]]
DependencyState = Literal["up", "down"]
ReadinessState = Literal["ready", "unready"]


class LivenessResponse(BaseModel):
    """The stable response contract for process liveness."""

    status: Literal["alive"]


class ReadinessResponse(BaseModel):
    """The stable response contract for dependency readiness."""

    status: ReadinessState
    dependencies: dict[str, DependencyState]


router = APIRouter(prefix="/health", tags=["health"])

async def _dependency_state(check: ReadinessCheck, timeout_seconds: float) -> DependencyState:
    try:
        result = await asyncio.wait_for(check(), timeout=timeout_seconds)
        return "up" if result else "down"
    except Exception:
        return "down"


@router.get(
    "/live",
    response_model=LivenessResponse,
    responses={200: {"model": LivenessResponse}},
)
async def liveness() -> LivenessResponse:
    """Report whether the API process can serve requests."""

    return LivenessResponse(status="alive")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(request: Request) -> JSONResponse:
    """Report aggregate dependency state without exposing connection details."""

    checks = cast(Mapping[str, ReadinessCheck], request.app.state.readiness_checks)
    timeout_seconds = cast(float, request.app.state.readiness_timeout_seconds)
    names = tuple(checks)
    states = await asyncio.gather(
        *(_dependency_state(checks[name], timeout_seconds) for name in names)
    )
    dependencies = dict(zip(names, states, strict=True))
    is_ready = all(state == "up" for state in states)
    result = ReadinessResponse(
        status="ready" if is_ready else "unready",
        dependencies=dependencies,
    )
    return JSONResponse(
        content=result.model_dump(mode="json"),
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
