"""FastAPI application entry point.

Wires:

* structlog configuration (via :func:`app.core.logging.configure_logging`)
* request-id middleware (adds ``X-Request-ID`` header + structlog contextvar)
* global exception handler that maps :class:`~app.core.errors.AppError` to
  the architecture §3 JSON envelope and falls back to ``SYS_003`` for any
  uncaught exception
* FastAPI ``lifespan`` that configures the DB engine, registers durable job
  handlers, and starts/stops the APScheduler singleton
* best-effort ``try/except ImportError`` mount for ``app.api.v1.router`` so
  that Batch 0 is standalone-testable even when the v1 router has not yet
  been built
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import bind_request_context, clear_request_context, configure_logging
from app.domain.consolidation.export import register_report_export_handler
from app.infra import jobs as jobs_module
from app.infra import scheduler as scheduler_module
from app.infra.db.session import configure_engine, dispose_engine, get_session_factory

__all__ = ["app", "create_app"]


_LOG = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a ``request_id`` per request.

    The id is stored on ``request.state.request_id``, echoed back as the
    ``X-Request-ID`` response header, and bound into the structlog context
    so every log line produced inside the request body inherits it.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        """Store configuration on the instance.

        Args:
            app: Downstream ASGI application.
            header_name: Header name for inbound/outbound request id.
        """
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Assign the request id, bind it to structlog, and clear on exit.

        Args:
            request: Inbound request.
            call_next: Next middleware / route handler.

        Returns:
            Response: The downstream response with ``X-Request-ID`` set.
        """
        incoming = request.headers.get(self._header_name)
        request_id = incoming or uuid4().hex
        request.state.request_id = request_id
        bind_request_context(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        response.headers[self._header_name] = request_id
        return response


def _build_envelope(error: AppError, request_id: str | None) -> dict[str, Any]:
    """Merge ``AppError.to_envelope`` with the caller's request id.

    Args:
        error: The raised :class:`AppError`.
        request_id: Request correlation id, or ``None`` when unavailable.

    Returns:
        dict[str, Any]: JSON-serializable envelope body.
    """
    payload = error.to_envelope()
    payload["request_id"] = request_id
    return payload


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle an :class:`AppError` by returning the architecture §3 envelope.

    Args:
        request: Inbound request.
        exc: Raised exception (narrowed to :class:`AppError`).

    Returns:
        JSONResponse: Response carrying the envelope and the error's HTTP status.
    """
    if not isinstance(exc, AppError):  # pragma: no cover — FastAPI dispatch guarantees the type
        return await _unhandled_exception_handler(request, exc)
    request_id = getattr(request.state, "request_id", None)
    _LOG.info(
        "app.error",
        code=exc.code,
        http_status=exc.http_status,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=_build_envelope(exc, request_id),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler — converts any uncaught exception to ``SYS_003``.

    Args:
        request: Inbound request.
        exc: Raised exception.

    Returns:
        JSONResponse: ``SYS_003`` envelope with HTTP 500.
    """
    request_id = getattr(request.state, "request_id", None)
    _LOG.error(
        "app.unhandled_exception",
        error=str(exc),
        type=type(exc).__name__,
        request_id=request_id,
    )
    fallback = AppError("SYS_003", f"{type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=fallback.http_status,
        content=_build_envelope(fallback, request_id),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan that wires startup and shutdown side effects.

    Args:
        app: The constructed FastAPI application.

    Yields:
        None: Control is returned to FastAPI between startup and shutdown.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_engine()
    jobs_module.register_all_handlers()
    # Reason: Batch 6 — register the report_export handler so async
    # export jobs can be dispatched by the worker.
    register_report_export_handler(
        session_factory=get_session_factory(),
        notification_factory=lambda _session: None,
    )
    scheduler_module.start()
    _LOG.info("app.startup", log_level=settings.log_level)
    try:
        yield
    finally:
        _LOG.info("app.shutdown")
        scheduler_module.shutdown()
        await dispose_engine()


def create_app() -> FastAPI:
    """Construct and return the FastAPI application.

    Registering the app through a factory (rather than at import time alone)
    keeps tests deterministic — each test file that needs its own engine can
    call :func:`create_app` afresh.

    Returns:
        FastAPI: The configured application.
    """
    settings = get_settings()
    application = FastAPI(
        title="BCMS Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Middleware ------------------------------------------------------
    application.add_middleware(RequestIDMiddleware, header_name=settings.request_id_header)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin] if settings.frontend_origin else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception handlers ----------------------------------------------
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    # --- Routers ---------------------------------------------------------
    try:
        from app.api.v1.router import router as api_v1_router  # type: ignore[import-not-found]

        application.include_router(api_v1_router, prefix="/api/v1")
    except ImportError:
        # Reason: Batch 0 is standalone; the v1 router may not exist yet.
        _LOG.info("app.v1_router_not_mounted")

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe used by the container runtime.

        Returns:
            dict[str, str]: ``{"status": "ok"}``.
        """
        return {"status": "ok"}

    return application


app = create_app()
