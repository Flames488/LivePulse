
from __future__ import annotations

import logging
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine


from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi.responses import JSONResponse
async def error_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc)})


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured Error Response Schema
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    request_id: str
    timestamp: str
    status: int
    error: str
    message: str
    path: str
    details: list[ErrorDetail] = []
    trace_id: str | None = None  # For distributed tracing (e.g. OpenTelemetry)


# ---------------------------------------------------------------------------
# Custom Exception Hierarchy
# ---------------------------------------------------------------------------

class AppBaseException(Exception):
    """Base for all application-level exceptions."""
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: list[ErrorDetail] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class NotFoundException(AppBaseException):
    http_status = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class UnauthorizedException(AppBaseException):
    http_status = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"


class ForbiddenException(AppBaseException):
    http_status = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"


class ConflictException(AppBaseException):
    http_status = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


class UnprocessableEntityException(AppBaseException):
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "UNPROCESSABLE_ENTITY"


class RateLimitException(AppBaseException):
    http_status = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "RATE_LIMIT_EXCEEDED"


class ServiceUnavailableException(AppBaseException):
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "SERVICE_UNAVAILABLE"


class BadRequestException(AppBaseException):
    http_status = status.HTTP_400_BAD_REQUEST
    error_code = "BAD_REQUEST"


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def _get_request_id(request: Request) -> str:
    """Extract or generate a unique request ID."""
    return (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or str(uuid.uuid4())
    )


def _get_trace_id(request: Request) -> str | None:
    """Extract distributed trace ID if present (e.g. from OpenTelemetry)."""
    return request.headers.get("X-Trace-ID") or request.headers.get("traceparent")


def _build_response(
    request: Request,
    *,
    http_status: int,
    error_code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    request_id = _get_request_id(request)
    body = ErrorResponse(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status=http_status,
        error=error_code,
        message=message,
        path=str(request.url.path),
        details=details or [],
        trace_id=_get_trace_id(request),
    )
    return JSONResponse(
        status_code=http_status,
        content=body.model_dump(),
        headers={"X-Request-ID": request_id},
    )

def register_error_handlers(app):
    @app.exception_handler(Exception)
    async def handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

def _log_error(
    request: Request,
    exc: Exception,
    *,
    level: int = logging.ERROR,
    include_traceback: bool = True,
) -> None:
    request_id = _get_request_id(request)
    extra = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "client_host": request.client.host if request.client else "unknown",
        "exception_type": type(exc).__name__,
    }
    msg = f"[{request_id}] {type(exc).__name__}: {exc}"
    if include_traceback and level >= logging.ERROR:
        msg += f"\n{traceback.format_exc()}"
    logger.log(level, msg, extra=extra)


# ---------------------------------------------------------------------------
# Optional Alert / Sentry Hook (plug in your own implementation)
# ---------------------------------------------------------------------------

AlertHook = Callable[[Request, Exception], Coroutine[Any, Any, None]]
_alert_hook: AlertHook | None = None


def register_alert_hook(hook: AlertHook) -> None:
    """Register an async callable that receives (request, exc) for critical errors."""
    global _alert_hook
    _alert_hook = hook


async def _maybe_alert(request: Request, exc: Exception) -> None:
    if _alert_hook:
        try:
            await _alert_hook(request, exc)
        except Exception as hook_exc:
            logger.warning(f"Alert hook raised an exception: {hook_exc}")


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------

async def _handle_app_exception(request: Request, exc: AppBaseException) -> JSONResponse:
    _log_error(request, exc, level=logging.WARNING, include_traceback=False)
    if exc.http_status >= 500:
        await _maybe_alert(request, exc)
    return _build_response(
        request,
        http_status=exc.http_status,
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
    )


async def _handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    _log_error(request, exc, level=logging.WARNING, include_traceback=False)
    return _build_response(
        request,
        http_status=exc.status_code,
        error_code=f"HTTP_{exc.status_code}",
        message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
    )


async def _handle_validation_exception(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        ErrorDetail(
            code=".".join(str(part) for part in err.get("loc", [])[1:]) or "unknown",
            message=err.get("msg", "Validation error"),
            field=".".join(str(part) for part in err.get("loc", [])[1:]) or None,
        )
        for err in exc.errors()
    ]
    _log_error(request, exc, level=logging.INFO, include_traceback=False)
    return _build_response(
        request,
        http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="VALIDATION_ERROR",
        message="Request validation failed.",
        details=details,
    )


async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    _log_error(request, exc, level=logging.ERROR, include_traceback=True)
    await _maybe_alert(request, exc)
    return _build_response(
        request,
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred. Please try again later.",
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def add_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers on the FastAPI application.

    Usage:
        app = FastAPI()
        add_exception_handlers(app)

    Optional alert hook (e.g. Sentry):
        async def sentry_hook(request, exc):
            sentry_sdk.capture_exception(exc)
        register_alert_hook(sentry_hook)
    """
    app.add_exception_handler(AppBaseException, _handle_app_exception)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_exception)
    app.add_exception_handler(Exception, _handle_unhandled_exception)

    logger.info("Exception handlers registered.")


# ---------------------------------------------------------------------------
# Middleware variant: attaches request_id to request state early in pipeline
# ---------------------------------------------------------------------------

async def request_id_middleware(request: Request, call_next):
    """
    Middleware that stamps every request with a unique ID and propagates it
    through response headers. Add via: app.middleware("http")(request_id_middleware)
    """
    request_id = _get_request_id(request)
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    app = FastAPI(title="Advanced Error Handling Demo")
    app.middleware("http")(request_id_middleware)
    add_exception_handlers(app)

    @app.get("/ok")
    async def ok():
        return {"status": "healthy"}

    @app.get("/not-found")
    async def not_found():
        raise NotFoundException("The requested resource does not exist.")

    @app.get("/forbidden")
    async def forbidden():
        raise ForbiddenException("You do not have permission to access this resource.")

    @app.get("/rate-limited")
    async def rate_limited():
        raise RateLimitException("Too many requests. Slow down.")

    @app.get("/crash")
    async def crash():
        raise RuntimeError("Something went very wrong.")

    @app.get("/validation-demo")
    async def validation_demo(age: int):
        return {"age": age}

    uvicorn.run(app, host="0.0.0.0", port=8000)