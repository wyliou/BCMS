"""Shared fixtures for :mod:`app.domain.audit` unit tests.

The audit unit tier cannot assume Postgres or aiosqlite is available, and
Batch 0 shipped no in-memory async engine. Instead, these tests substitute
:class:`AuditRepo` with a lightweight in-memory fake that implements the
same four async methods. This is NOT cross-module mocking — the fake is a
test-owned repo double that exercises the real :class:`AuditService` and
real hash-chain logic end-to-end.

The real repo is exercised separately in
``tests/integration/audit/test_repo.py`` against a real Postgres backend.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit.models import AuditLog
from app.domain.audit.repo import AuditFilters, Page


class InMemoryAuditRepo:
    """In-memory stand-in for :class:`app.domain.audit.repo.AuditRepo`.

    Implements the same four async methods used by
    :class:`AuditService`. Rows are stored in insertion order; ``insert``
    assigns a strictly increasing ``sequence_no`` so the service's hash
    chain advances exactly as it would against a real database.
    """

    def __init__(self) -> None:
        """Initialize an empty row store."""
        self.rows: list[AuditLog] = []
        self._next_seq: int = 1

    async def fetch_page(self, filters: AuditFilters) -> Page[AuditLog]:
        """Return a filtered + paginated view of the in-memory rows.

        Args:
            filters (AuditFilters): Query filters and pagination params.

        Returns:
            Page[AuditLog]: Paginated snapshot of matching rows.
        """
        selected = [r for r in self.rows if self._matches(r, filters)]
        # Reason: match real repo — order by sequence_no DESC.
        selected.sort(key=lambda r: r.sequence_no, reverse=True)
        offset = (filters.page - 1) * filters.size
        page_items = selected[offset : offset + filters.size]
        return Page(
            items=page_items,
            total=len(selected),
            page=filters.page,
            size=filters.size,
        )

    async def fetch_range(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[AuditLog]:
        """Return all rows in the date range, ordered by ``sequence_no`` ASC.

        Args:
            from_dt (datetime | None): Inclusive lower bound on ``occurred_at``.
            to_dt (datetime | None): Inclusive upper bound on ``occurred_at``.

        Returns:
            list[AuditLog]: Matching rows sorted by ``sequence_no`` ascending.
        """
        out = []
        for r in self.rows:
            if from_dt is not None and r.occurred_at < from_dt:
                continue
            if to_dt is not None and r.occurred_at > to_dt:
                continue
            out.append(r)
        out.sort(key=lambda r: r.sequence_no)
        return out

    async def get_latest(self) -> AuditLog | None:
        """Return the row with the highest ``sequence_no``, or ``None``.

        Returns:
            AuditLog | None: Latest row or ``None`` when the store is empty.
        """
        if not self.rows:
            return None
        return max(self.rows, key=lambda r: r.sequence_no)

    async def insert(self, row: AuditLog) -> AuditLog:
        """Assign a sequence number and append the row to the store.

        Args:
            row (AuditLog): Row to insert (``sequence_no`` may be ``None``).

        Returns:
            AuditLog: Same instance with ``sequence_no`` populated.
        """
        row.sequence_no = self._next_seq
        self._next_seq += 1
        self.rows.append(row)
        return row

    @staticmethod
    def _matches(row: AuditLog, filters: AuditFilters) -> bool:
        """Return ``True`` iff ``row`` satisfies every non-``None`` filter.

        Args:
            row (AuditLog): Candidate row.
            filters (AuditFilters): Filter values (``None`` means wildcard).

        Returns:
            bool: Match result.
        """
        if filters.user_id is not None and row.user_id != filters.user_id:
            return False
        if filters.action is not None and row.action != filters.action:
            return False
        if filters.resource_type is not None and row.resource_type != filters.resource_type:
            return False
        if filters.resource_id is not None and row.resource_id != filters.resource_id:
            return False
        if filters.from_dt is not None and row.occurred_at < filters.from_dt:
            return False
        if filters.to_dt is not None and row.occurred_at > filters.to_dt:
            return False
        return True


@pytest.fixture
def fake_repo() -> InMemoryAuditRepo:
    """Fresh per-test in-memory repo substitute.

    Returns:
        InMemoryAuditRepo: Empty store.
    """
    return InMemoryAuditRepo()


@pytest.fixture
def fake_session() -> Any:
    """Return a minimal :class:`AsyncSession`-shaped stand-in.

    :class:`AuditService.record` calls ``self._db.flush()`` once after
    updating ``hash_chain_value``. The stand-in's ``flush`` is an async
    no-op — no real flush work is needed because the fake repo already
    owns the row store.

    Returns:
        MagicMock: A mock with an async ``flush`` method.
    """
    mock = MagicMock(spec=AsyncSession)

    async def _flush(*_: object, **__: object) -> None:
        """No-op async flush used by the fake session."""
        return None

    mock.flush.side_effect = _flush
    return mock


@pytest_asyncio.fixture
async def audit_service_and_repo(
    fake_session: Any, fake_repo: InMemoryAuditRepo
) -> AsyncIterator[tuple[Any, InMemoryAuditRepo]]:
    """Yield an :class:`AuditService` wired to the in-memory repo.

    The real :class:`AuditService` is instantiated with the fake session
    and then has its private ``_repo`` attribute swapped for the
    in-memory double. All business logic (hash chain, serialization,
    verify) runs against the real code.

    Yields:
        tuple[AuditService, InMemoryAuditRepo]: Service + the backing fake.
    """
    from app.domain.audit.service import AuditService

    service = AuditService(fake_session)
    service._repo = fake_repo  # type: ignore[assignment]
    yield service, fake_repo
