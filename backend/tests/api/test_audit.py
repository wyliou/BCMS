"""API-level tests for :mod:`app.api.v1.audit`.

These tests use a FastAPI instance that dependency-overrides
:func:`app.infra.db.session.get_session` with an in-memory fake so the
routes exercise the real router and the real :class:`AuditService`
plumbing without requiring Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.audit import router as audit_router
from app.domain.audit.actions import AuditAction
from app.domain.audit.models import AuditLog
from app.domain.audit.service import _GENESIS_PREV_HASH, AuditService
from app.infra.crypto import chain_hash
from app.infra.db.session import get_session


# ------------------------------------------------------------ fake session
class _FakeRow:
    """Lightweight stand-in for a :class:`AuditLog` row.

    The API reads ``model_validate(row)`` via Pydantic's ``from_attributes``
    mode, so all the read code ever does is attribute access — we don't
    need a real ORM instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Copy every keyword into an attribute."""
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeSession:
    """Minimal async session stand-in for route tests.

    Tracks a per-instance ``rows`` list and implements the handful of
    methods the :class:`AuditService` and :class:`AuditRepo` touch.
    """

    def __init__(self, rows: list[AuditLog]) -> None:
        """Seed with a fixed list of rows."""
        self.rows = rows

    async def flush(self) -> None:
        """Async no-op — the fake repo owns row storage."""
        return None


class _RowRepo:
    """Tiny in-memory repo double used by the route tests."""

    def __init__(self, rows: list[AuditLog]) -> None:
        """Seed with pre-built rows."""
        self.rows = rows

    async def fetch_page(self, filters: Any) -> Any:
        """Return a filtered + paginated snapshot of the seeded rows."""
        from app.domain.audit.repo import Page

        def _ok(r: AuditLog) -> bool:
            if filters.action is not None and r.action != filters.action:
                return False
            return True

        selected = [r for r in self.rows if _ok(r)]
        return Page(items=selected, total=len(selected), page=1, size=50)

    async def fetch_range(self, from_dt: Any, to_dt: Any) -> list[AuditLog]:
        """Return all seeded rows sorted by ``sequence_no`` ASC."""
        return sorted(self.rows, key=lambda r: r.sequence_no)

    async def get_latest(self) -> AuditLog | None:
        """Return the highest-``sequence_no`` row, or ``None``."""
        if not self.rows:
            return None
        return max(self.rows, key=lambda r: r.sequence_no)

    async def insert(self, row: AuditLog) -> AuditLog:
        """No-op insert — unused by read-only routes but present for parity."""
        self.rows.append(row)
        return row


# ------------------------------------------------------------ app fixtures
def _build_valid_row(seq: int, prev_hash: bytes, action: AuditAction) -> AuditLog:
    """Return a row with a correctly computed ``hash_chain_value``.

    Args:
        seq: Sequence number to assign.
        prev_hash: Previous row's ``hash_chain_value``.
        action: The audit action enum.

    Returns:
        AuditLog: Ready-to-verify ORM instance.
    """
    row = AuditLog(
        id=uuid4(),
        sequence_no=seq,
        user_id=None,
        action=str(action.value),
        resource_type="cycle",
        resource_id=None,
        ip_address=None,
        details={"seq": seq},
        prev_hash=prev_hash,
        hash_chain_value=_GENESIS_PREV_HASH,  # placeholder
        occurred_at=datetime(2026, 1, 1, 0, 0, seq, tzinfo=timezone.utc),
    )
    payload = AuditService._serialize_for_chain(row)
    row.hash_chain_value = chain_hash(prev_hash, payload)
    return row


def _seed_chain(n: int = 3) -> list[AuditLog]:
    """Build a valid n-row chain starting from the genesis sentinel."""
    rows: list[AuditLog] = []
    prev = _GENESIS_PREV_HASH
    for i in range(n):
        row = _build_valid_row(i + 1, prev, AuditAction.LOGIN_SUCCESS)
        prev = row.hash_chain_value
        rows.append(row)
    return rows


@pytest.fixture
def seeded_rows() -> list[AuditLog]:
    """Three valid rows ready for route testing."""
    return _seed_chain(3)


@pytest.fixture
def audit_app(seeded_rows: list[AuditLog]) -> FastAPI:
    """Build a FastAPI app with the audit router mounted.

    The app overrides :func:`get_session` so every request sees a
    :class:`_FakeSession` backed by the seeded rows. The real
    :class:`AuditService` is instantiated; only the repo is swapped for
    the lightweight double via ``_repo`` assignment on the ``AuditService``
    class method — we patch at construction time via a subclass.
    """
    application = FastAPI()
    application.include_router(audit_router, prefix="/api/v1")

    shared_repo = _RowRepo(seeded_rows)

    async def _override_session() -> AsyncIterator[_FakeSession]:
        yield _FakeSession(seeded_rows)

    # Reason: the real AuditService always builds its own AuditRepo — we
    # need routes to use our in-memory double. Monkey-patch the class to
    # swap repos during construction.
    original_init = AuditService.__init__

    def _patched_init(self: AuditService, db: Any) -> None:
        """Initialize the service and swap in the shared fake repo."""
        original_init(self, db)
        self._repo = shared_repo  # type: ignore[assignment]

    AuditService.__init__ = _patched_init  # type: ignore[method-assign]
    application.state._original_audit_init = original_init  # type: ignore[attr-defined]

    application.dependency_overrides[get_session] = _override_session
    return application


@pytest.fixture
async def client(audit_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Yield an :class:`httpx.AsyncClient` wired to the audit app."""
    transport = httpx.ASGITransport(app=audit_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # Reason: restore AuditService.__init__ so other tests see the real impl.
    original = audit_app.state._original_audit_init  # type: ignore[attr-defined]
    AuditService.__init__ = original  # type: ignore[method-assign]


# -------------------------------------------------------------- tests
async def test_list_audit_logs_returns_paginated_shape(
    client: httpx.AsyncClient,
) -> None:
    """GET /audit-logs returns 200 with items/total/page/size."""
    response = await client.get("/api/v1/audit-logs")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"items", "total", "page", "size"}
    assert body["total"] == 3


async def test_list_audit_logs_filter_by_action(
    client: httpx.AsyncClient,
) -> None:
    """Filtering by action returns only matching rows."""
    response = await client.get("/api/v1/audit-logs?action=LOGIN_SUCCESS")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert all(item["action"] == "LOGIN_SUCCESS" for item in body["items"])


async def test_list_audit_logs_filter_action_no_match(
    client: httpx.AsyncClient,
) -> None:
    """A non-matching filter yields zero rows."""
    response = await client.get("/api/v1/audit-logs?action=LOGOUT")
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_verify_chain_returns_verified_true(
    client: httpx.AsyncClient,
) -> None:
    """The verify route returns a ChainVerification shape with verified=true."""
    response = await client.get("/api/v1/audit-logs/verify")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verified"] is True
    assert body["chain_length"] == 3
    assert isinstance(body["range"], list)
    assert len(body["range"]) == 2


async def test_export_returns_csv_content_disposition(
    client: httpx.AsyncClient,
) -> None:
    """The export route returns a CSV with the correct download headers."""
    response = await client.get("/api/v1/audit-logs/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition
    assert "audit_logs.csv" in disposition


@pytest.mark.skip(reason="Batch 2 wires RBAC — ITSecurityAuditor enforcement deferred")
async def test_list_audit_logs_rbac_requires_it_security_auditor() -> None:
    """Placeholder for Batch 2 — deferred until the real RBAC dep lands."""
