"""API-level tests for :mod:`app.main`.

Covers the request-id middleware, the global exception handler, and the
``SYS_003`` fallback path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.errors import (
    AppError,
    BatchValidationError,
    ConflictError,
)
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield an :class:`httpx.AsyncClient` wired to the in-process app."""
    # Reason: FastAPI's exception middleware converts uncaught exceptions to
    # 500 responses, but httpx's default ASGI transport re-raises them on
    # the test side. Disable that re-raise so our SYS_003 fallback path is
    # observable in tests.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@app.get("/_test/ok")
async def _ok() -> dict[str, str]:
    """Baseline healthy route used by tests."""
    return {"value": "ok"}


@app.get("/_test/app_error")
async def _app_error_route() -> dict[str, str]:
    """Raise a typed :class:`ConflictError`."""
    raise ConflictError("CYCLE_001", "dup")


@app.get("/_test/batch_error")
async def _batch_error_route() -> dict[str, str]:
    """Raise a :class:`BatchValidationError` carrying row errors."""
    raise BatchValidationError(
        "UPLOAD_007",
        errors=[{"row": 1, "code": "UPLOAD_003", "reason": "dept"}],
    )


@app.get("/_test/boom")
async def _boom() -> dict[str, str]:
    """Raise a plain uncaught exception."""
    raise RuntimeError("boom")


async def test_healthz_returns_ok(client: httpx.AsyncClient) -> None:
    """Baseline smoke test for the liveness probe."""
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_request_id_header_present(client: httpx.AsyncClient) -> None:
    """Every response carries an ``X-Request-ID`` header."""
    response = await client.get("/healthz")
    assert response.headers.get("X-Request-ID")


async def test_request_id_unique_per_request(client: httpx.AsyncClient) -> None:
    """Two requests get different request ids."""
    first = await client.get("/healthz")
    second = await client.get("/healthz")
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_app_error_returns_envelope(client: httpx.AsyncClient) -> None:
    """Typed :class:`AppError` routes through the global handler."""
    response = await client.get("/_test/app_error")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "CYCLE_001"
    assert body["request_id"] == response.headers["X-Request-ID"]


async def test_batch_validation_error_includes_details(
    client: httpx.AsyncClient,
) -> None:
    """BatchValidationError surfaces row-level details in the envelope."""
    response = await client.get("/_test/batch_error")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "UPLOAD_007"
    assert body["error"]["details"] == [{"row": 1, "code": "UPLOAD_003", "reason": "dept"}]


async def test_unhandled_exception_becomes_sys_003(
    client: httpx.AsyncClient,
) -> None:
    """Any uncaught :class:`Exception` becomes ``SYS_003``."""
    response = await client.get("/_test/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "SYS_003"


def test_app_error_envelope_shape_contract() -> None:
    """Unit-level contract for :meth:`AppError.to_envelope`."""
    err = AppError("SYS_003", "oops")
    envelope = err.to_envelope()
    assert set(envelope["error"].keys()) == {"code", "message", "details"}
