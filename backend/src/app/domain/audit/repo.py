"""Repository (data-access layer) for :class:`app.domain.audit.models.AuditLog`.

This module owns *reads* and the low-level ``INSERT`` path for the audit
log table. All business rules — hash chain advancement, action routing,
RBAC — live in :class:`app.domain.audit.service.AuditService`.

The repository exposes four async methods:

* :meth:`AuditRepo.fetch_page` — filtered, paginated read used by the
  ``GET /audit-logs`` route.
* :meth:`AuditRepo.fetch_range` — ordered (by ``sequence_no``) range read
  used by ``verify_chain`` and ``/export``.
* :meth:`AuditRepo.get_latest` — returns the row with the highest
  ``sequence_no``; used by :meth:`AuditService.record` to obtain
  ``prev_hash``.
* :meth:`AuditRepo.insert` — low-level INSERT helper. Does **not** commit.

Filter validation (e.g. ``to_dt < from_dt``) raises ``AppError("AUDIT_002")``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.audit.models import AuditLog

__all__ = ["AuditFilters", "AuditRepo", "Page"]


T = TypeVar("T")


@dataclass
class AuditFilters:
    """Filter parameters for audit log queries.

    Attributes:
        user_id (UUID | None): Filter to a specific user.
        action (str | None): Filter to a specific ``AuditAction`` value.
        resource_type (str | None): Filter to a resource type.
        resource_id (UUID | None): Filter to a specific resource ID.
        from_dt (datetime | None): Start of ``occurred_at`` range (inclusive, UTC).
        to_dt (datetime | None): End of ``occurred_at`` range (inclusive, UTC).
        page (int): Page number, 1-based. Defaults to 1.
        size (int): Page size, max 200. Defaults to 50.
    """

    user_id: UUID | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: UUID | None = None
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    page: int = 1
    size: int = 50


@dataclass
class Page(Generic[T]):
    """Paginated result wrapper.

    Attributes:
        items (list[T]): Page items.
        total (int): Total matching rows.
        page (int): Current page number.
        size (int): Page size.
    """

    items: list[T] = field(default_factory=list[T])
    total: int = 0
    page: int = 1
    size: int = 50


class AuditRepo:
    """Data-access layer for :class:`AuditLog`.

    The repository never commits — transaction boundaries belong to the
    caller (typically :class:`app.domain.audit.service.AuditService`). The
    write path in :meth:`insert` simply adds the ORM instance to the active
    session and flushes so that DB-assigned values (``sequence_no``, server
    defaults) are visible before the chain hash is computed.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active async session.

        Args:
            db (AsyncSession): Active async session managed by the caller.
        """
        self._db = db

    # ------------------------------------------------------------------ reads
    async def fetch_page(self, filters: AuditFilters) -> Page[AuditLog]:
        """Fetch a paginated, filtered page of audit log rows.

        Filters that are ``None`` are skipped; the remaining predicates are
        AND-combined. Ordering is deterministic on ``sequence_no DESC`` so
        that the most recent rows land on page 1.

        Args:
            filters (AuditFilters): Query filters and pagination params.

        Returns:
            Page[AuditLog]: Paginated audit log rows plus the total count.

        Raises:
            AppError: code=``AUDIT_002`` when filter params are invalid
                (e.g. ``to_dt < from_dt``, non-positive page/size).
        """
        self._validate_filters(filters)
        conditions = self._build_conditions(filters)

        count_stmt: Any = select(func.count()).select_from(AuditLog)
        list_stmt: Any = select(AuditLog)
        if conditions:
            where = and_(*conditions)
            count_stmt = count_stmt.where(where)
            list_stmt = list_stmt.where(where)
        offset = (filters.page - 1) * filters.size
        list_stmt = (
            list_stmt.order_by(AuditLog.sequence_no.desc()).offset(offset).limit(filters.size)
        )

        total_row = await self._db.execute(count_stmt)
        total = int(total_row.scalar_one() or 0)
        items_row = await self._db.execute(list_stmt)
        items = list(items_row.scalars().all())

        return Page(items=items, total=total, page=filters.page, size=filters.size)

    async def fetch_range(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[AuditLog]:
        """Fetch all audit log rows in a date range ordered by ``sequence_no``.

        Used by :meth:`AuditService.verify_chain` and the CSV export route.
        No pagination — returns every matching row.

        Args:
            from_dt (datetime | None): Range start (inclusive). ``None`` = from the beginning.
            to_dt (datetime | None): Range end (inclusive). ``None`` = through the latest.

        Returns:
            list[AuditLog]: All rows in the range sorted by ``sequence_no`` ASC.

        Raises:
            AppError: code=``AUDIT_002`` if ``to_dt < from_dt``.
        """
        if from_dt is not None and to_dt is not None and to_dt < from_dt:
            raise AppError("AUDIT_002", "to_dt must be >= from_dt")

        stmt: Any = select(AuditLog)
        conditions: list[Any] = []
        if from_dt is not None:
            conditions.append(AuditLog.occurred_at >= from_dt)
        if to_dt is not None:
            conditions.append(AuditLog.occurred_at <= to_dt)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(AuditLog.sequence_no.asc())

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self) -> AuditLog | None:
        """Return the audit log row with the highest ``sequence_no``.

        Used by :meth:`AuditService.record` to obtain ``prev_hash`` for the
        next row. Returns ``None`` when the table is empty (genesis case).

        Returns:
            AuditLog | None: Latest row, or ``None`` if no rows exist.
        """
        stmt = select(AuditLog).order_by(AuditLog.sequence_no.desc()).limit(1)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    # ------------------------------------------------------------------ writes
    async def insert(self, row: AuditLog) -> AuditLog:
        """Add a new :class:`AuditLog` to the session and flush.

        Does NOT commit — the caller (:class:`AuditService`) owns transaction
        boundaries per CR-006. Flushing forces the DB to assign
        ``sequence_no`` so the service can cross-check the value used in the
        hash payload.

        Args:
            row (AuditLog): Fully populated audit log row. ``sequence_no`` may
                be ``None`` (BIGSERIAL will assign one on flush).

        Returns:
            AuditLog: The same ORM instance, now with ``sequence_no`` set.
        """
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    # ----------------------------------------------------------------- internals
    @staticmethod
    def _validate_filters(filters: AuditFilters) -> None:
        """Raise ``AUDIT_002`` if filter params are malformed.

        Args:
            filters (AuditFilters): Filters to validate.

        Raises:
            AppError: code=``AUDIT_002`` on any validation failure.
        """
        if filters.page < 1:
            raise AppError("AUDIT_002", "page must be >= 1")
        if filters.size < 1 or filters.size > 200:
            raise AppError("AUDIT_002", "size must be between 1 and 200")
        if (
            filters.from_dt is not None
            and filters.to_dt is not None
            and filters.to_dt < filters.from_dt
        ):
            raise AppError("AUDIT_002", "to_dt must be >= from_dt")

    @staticmethod
    def _build_conditions(filters: AuditFilters) -> list[Any]:
        """Translate a :class:`AuditFilters` into a list of SQLAlchemy predicates.

        Args:
            filters (AuditFilters): Filter parameters.

        Returns:
            list[Any]: Predicates to be combined via ``and_``.
        """
        conditions: list[Any] = []
        if filters.user_id is not None:
            conditions.append(AuditLog.user_id == filters.user_id)
        if filters.action is not None:
            conditions.append(AuditLog.action == filters.action)
        if filters.resource_type is not None:
            conditions.append(AuditLog.resource_type == filters.resource_type)
        if filters.resource_id is not None:
            conditions.append(AuditLog.resource_id == filters.resource_id)
        if filters.from_dt is not None:
            conditions.append(AuditLog.occurred_at >= filters.from_dt)
        if filters.to_dt is not None:
            conditions.append(AuditLog.occurred_at <= filters.to_dt)
        return conditions
