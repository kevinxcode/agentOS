"""Cookie-only authentication endpoints and reusable full-session authorization."""

from collections.abc import AsyncIterator, Awaitable, Callable
from hmac import compare_digest
from ipaddress import ip_address
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from agentos.auth.models import AdminUser
from agentos.auth.schemas import (
    AuthenticatedResponse,
    AuthStateResponse,
    CodeRequest,
    ConfirmationResponse,
    EnrollmentResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
)
from agentos.auth.service import FULL_SECONDS, PREAUTH_SECONDS, AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_NAME = "agentos_session"
logger = structlog.get_logger(__name__)
CLIENT_IP_HEADER = "x-agentos-client-ip"
PROXY_SECRET_HEADER = "x-agentos-proxy-secret"


def client_ip(request: Request) -> str:
    """Accept a forwarded client only across the authenticated web-to-API boundary."""

    peer = request.client.host if request.client else "unknown"
    configured = request.app.state.settings.auth_proxy_secret
    supplied = request.headers.get(PROXY_SECRET_HEADER)
    forwarded = request.headers.get(CLIENT_IP_HEADER)
    if configured is None or supplied is None or forwarded is None:
        return peer
    if not compare_digest(configured, supplied):
        return peer
    try:
        return str(ip_address(forwarded))
    except ValueError:
        return peer


async def get_auth_service(request: Request) -> AsyncIterator[AuthService]:
    async with request.app.state.session_factory() as db:
        yield AuthService(
            db,
            request.app.state.settings,
            request_id=request.state.request_id,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            token=request.cookies.get(COOKIE_NAME),
        )


Service = Annotated[AuthService, Depends(get_auth_service)]


async def execute[T](
    service: AuthService,
    action: str,
    operation: Callable[[], Awaitable[T]],
) -> T:
    try:
        result = await operation()
        service.audit(action, "success")
        # Durably revoke/consume credentials before any new cookie can be sent.
        await service.db.commit()
        return result
    except AuthError as error:
        await service.db.rollback()
        service.audit(action, "rate_limited" if error.status == 429 else "denied")
        await service.db.commit()
        detail = {
            401: "Authentication required or credentials invalid",
            409: "TOTP is already enrolled",
            429: "Too many attempts; try again later",
        }[error.status]
        raise HTTPException(
            status_code=error.status,
            detail=detail,
            headers={"Retry-After": "60"} if error.status == 429 else None,
        ) from None
    except Exception as error:
        # Roll back the operation first, then record only a safe outcome in a fresh
        # transaction. Never include exception text: DB/crypto errors can echo input.
        try:
            await service.db.rollback()
        except Exception as rollback_error:
            logger.error(
                "auth_operation_error",
                request_id=service.request_id,
                action=action,
                error_type=type(error).__name__,
                rollback_error_type=type(rollback_error).__name__,
                audit_recorded=False,
            )
            raise error.with_traceback(error.__traceback__)
        try:
            service.audit(action, "error")
            await service.db.commit()
        except Exception as audit_error:
            try:
                await service.db.rollback()
            except Exception as rollback_error:
                logger.error(
                    "auth_operation_error",
                    request_id=service.request_id,
                    action=action,
                    error_type=type(error).__name__,
                    audit_error_type=type(audit_error).__name__,
                    rollback_error_type=type(rollback_error).__name__,
                    audit_recorded=False,
                )
            else:
                logger.error(
                    "auth_operation_error",
                    request_id=service.request_id,
                    action=action,
                    error_type=type(error).__name__,
                    audit_error_type=type(audit_error).__name__,
                    audit_recorded=False,
                )
        else:
            logger.error(
                "auth_operation_error",
                request_id=service.request_id,
                action=action,
                error_type=type(error).__name__,
                audit_recorded=True,
            )
        raise


def set_cookie(response: Response, service: AuthService, token: str, *, full: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=FULL_SECONDS if full else PREAUTH_SECONDS,
        httponly=True,
        secure=service.settings.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, service: Service) -> dict[str, object]:
    result, token = await execute(
        service, "auth.login", lambda: service.login(body.email, body.password.get_secret_value())
    )
    set_cookie(response, service, token, full=False)
    return result


@router.post("/totp/enroll", response_model=EnrollmentResponse)
async def enroll(service: Service) -> dict[str, object]:
    return await execute(service, "auth.totp.enrollment_started", service.enroll)


@router.post("/totp/confirm", response_model=ConfirmationResponse)
async def confirm(body: CodeRequest, response: Response, service: Service) -> dict[str, object]:
    result, token = await execute(
        service,
        "auth.totp.enrolled",
        lambda: service.verify_totp(body.code.get_secret_value(), confirm=True),
    )
    set_cookie(response, service, token, full=True)
    return result


@router.post("/totp/verify", response_model=AuthenticatedResponse)
async def verify(body: CodeRequest, response: Response, service: Service) -> dict[str, object]:
    result, token = await execute(
        service,
        "auth.totp.verified",
        lambda: service.verify_totp(body.code.get_secret_value(), confirm=False),
    )
    set_cookie(response, service, token, full=True)
    return result


@router.post("/recovery", response_model=AuthenticatedResponse)
async def recovery(body: CodeRequest, response: Response, service: Service) -> dict[str, object]:
    result, token = await execute(
        service, "auth.recovery.used", lambda: service.recover(body.code.get_secret_value())
    )
    set_cookie(response, service, token, full=True)
    return result


@router.post("/logout", status_code=204)
async def logout(response: Response, service: Service) -> None:
    await execute(service, "auth.logout", service.logout)
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        secure=service.settings.cookie_secure,
        samesite="strict",
    )


@router.get("/me", response_model=MeResponse)
async def me(service: Service) -> dict[str, object]:
    return await execute(service, "auth.session.checked", service.me)


@router.get("/state", response_model=AuthStateResponse)
async def state(service: Service) -> dict[str, object]:
    return await service.state()


async def require_admin(service: Service) -> AdminUser:
    """Task 7 and protected API routes must use this dependency, never cookie presence."""
    _, admin = await execute(service, "auth.session.checked", lambda: service.current("full"))
    return admin
