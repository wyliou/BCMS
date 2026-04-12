"""Per-role dashboard service (FR-004, FR-014).

The :class:`DashboardService` returns a per-filing-unit status list for a
cycle, scoped to the authenticated user's ``scoped_org_units`` (CR-011).
CompanyReviewer callers receive a summary-only response per PRD §4.14
with ``items=[]``.

The service intentionally avoids N+1 — the inner
:meth:`_collect_rows` helper makes a small number of targeted queries
(one per table) and joins them in Python. That keeps the implementation
portable against both the Postgres integration tier and the in-memory
FakeSession used by unit tests, while still hitting the ≤5s latency
target on realistic org sizes (≤100 filing units).

Stale fallback (FR-014)
-----------------------
If the primary query raises :class:`InfraError`, the service returns a
:class:`DashboardResponse` with ``stale=True`` and empty ``items``. No
persistent snapshot table exists yet; the caller sees ``stale=True`` so
the UI can display a soft warning. Any other exception propagates
unchanged.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InfraError
from app.core.security.models import OrgUnit, User
from app.core.security.rbac import ALL_SCOPES, scoped_org_units
from app.core.security.roles import Role
from app.domain.budget_uploads.models import BudgetUpload
from app.domain.cycles.models import BudgetCycle, CycleState
from app.domain.notifications.models import ResubmitRequest
from app.domain.templates.models import ExcelTemplate
from app.infra.db.repos.budget_uploads_query import unsubmitted_for_cycle

__all__ = [
    "DashboardFilters",
    "DashboardItem",
    "DashboardResponse",
    "DashboardService",
    "DashboardStatus",
]


_LOG = structlog.get_logger(__name__)


DashboardStatus = Literal[
    "not_downloaded",
    "downloaded",
    "uploaded",
    "resubmit_requested",
]


class DashboardItem(BaseModel):
    """Single per-filing-unit row in the dashboard response.

    Attributes:
        org_unit_id: Filing unit UUID.
        org_unit_name: Human-readable unit name for display.
        status: One of the four FR-004 status values.
        last_uploaded_at: ``uploaded_at`` of the latest budget upload or
            ``None`` when no upload has been received yet.
        version: Upload version number (``None`` before first upload).
    """

    model_config = ConfigDict(from_attributes=True)

    org_unit_id: UUID
    org_unit_name: str
    status: DashboardStatus
    last_uploaded_at: str | None = None
    version: int | None = None


class DashboardFilters(BaseModel):
    """Filter / sort / pagination options for :meth:`DashboardService.status_for_user`.

    Attributes:
        status: Optional status filter. Only rows whose computed status
            equals this value are returned.
        org_unit_id: Optional filter — restrict to a single org unit id.
        sort: Sort key. ``last_uploaded_at`` (default, desc) or
            ``org_unit_code`` (ascending).
        limit: Max rows returned.
        offset: Rows to skip.
    """

    status: DashboardStatus | None = None
    org_unit_id: UUID | None = None
    sort: Literal["last_uploaded_at", "org_unit_code"] = "last_uploaded_at"
    limit: int = 100
    offset: int = 0


class DashboardResponse(BaseModel):
    """Aggregated dashboard payload returned to the route layer.

    Attributes:
        items: Per-filing-unit rows (scoped to the caller). Empty for
            CompanyReviewer and when the cycle sentinel fires.
        sentinel: ``'尚未開放週期'`` when the cycle is Draft or missing.
        stale: ``True`` when the primary query raised and the service
            returned a fallback response.
        summary: Aggregate summary populated only for CompanyReviewer.
    """

    items: list[DashboardItem] = []
    sentinel: str | None = None
    stale: bool = False
    summary: dict[str, int] | None = None


class DashboardService:
    """Facade that resolves per-user dashboard rows for a cycle.

    Request-scoped; built with the caller's active :class:`AsyncSession`.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the service.

        Args:
            db: Active async SQLAlchemy session.
        """
        self._db = db

    # ================================================================
    #                           public API
    # ================================================================
    async def status_for_user(
        self,
        *,
        cycle_id: UUID,
        user: User,
        filters: DashboardFilters | None = None,
    ) -> DashboardResponse:
        """Return the scoped dashboard response for ``user`` on ``cycle_id``.

        Resolves the user's scoped org units, applies the FR-014
        CompanyReviewer summary-only behaviour, and assembles the list
        of per-unit rows. Any :class:`InfraError` triggers the FR-014
        stale fallback.

        Args:
            cycle_id: Target cycle UUID.
            user: Authenticated caller.
            filters: Optional filter + sort + pagination options.

        Returns:
            DashboardResponse: The assembled response payload.
        """
        filters = filters or DashboardFilters()

        # --- 1. Empty cycle sentinel -----------------------------------
        cycle = await self._db.get(BudgetCycle, cycle_id)
        if cycle is None or CycleState(cycle.status) == CycleState.draft:
            return DashboardResponse(sentinel="尚未開放週期", items=[])

        # --- 2. CompanyReviewer summary-only path ----------------------
        roles = user.role_set()
        if Role.CompanyReviewer in roles and not roles.intersection(
            {Role.SystemAdmin, Role.FinanceAdmin, Role.HRAdmin}
        ):
            return await self._build_summary_response(cycle_id=cycle_id)

        # --- 3. Scope resolution (CR-011) ------------------------------
        scope = await scoped_org_units(user, self._db)

        # --- 4. Collect rows (with stale fallback on InfraError) -------
        try:
            items = await self._collect_rows(cycle_id=cycle_id, scope=scope)
        except InfraError as exc:
            # Reason: FR-014 stale fallback. No persistent snapshot store
            # ships in Batch 6 — mark stale so the UI can display a
            # soft warning rather than a hard failure.
            _LOG.warning(
                "dashboard.stale_fallback",
                cycle_id=str(cycle_id),
                error=exc.code,
            )
            return DashboardResponse(items=[], stale=True)

        # --- 5. Filter / sort / paginate -------------------------------
        items = self._apply_filters(items, filters)
        return DashboardResponse(items=items)

    # ================================================================
    #                          internals
    # ================================================================
    async def _collect_rows(
        self,
        *,
        cycle_id: UUID,
        scope: frozenset[UUID] | set[UUID],
    ) -> list[DashboardItem]:
        """Assemble dashboard rows for every scoped filing unit.

        Args:
            cycle_id: Target cycle.
            scope: RBAC-resolved org-unit id set (or :data:`ALL_SCOPES`).

        Returns:
            list[DashboardItem]: One row per scoped filing unit.
        """
        units = await self._list_filing_units(scope=scope)
        if not units:
            return []

        # CR-026: shared unsubmitted query — units with zero uploads.
        unsubmitted_ids = set(await unsubmitted_for_cycle(self._db, cycle_id))

        uploads_by_unit = await self._latest_uploads_by_unit(cycle_id=cycle_id)
        templates_by_unit = await self._templates_by_unit(cycle_id=cycle_id)
        open_resubmits = await self._open_resubmit_ids(cycle_id=cycle_id)

        items: list[DashboardItem] = []
        for unit in units:
            status: DashboardStatus
            upload = uploads_by_unit.get(unit.id)
            template = templates_by_unit.get(unit.id)

            if unit.id in open_resubmits:
                status = "resubmit_requested"
            elif upload is not None and unit.id not in unsubmitted_ids:
                status = "uploaded"
            elif template is None or template.download_count == 0:
                status = "not_downloaded"
            else:
                status = "downloaded"

            items.append(
                DashboardItem(
                    org_unit_id=unit.id,
                    org_unit_name=unit.name,
                    status=status,
                    last_uploaded_at=(
                        upload.uploaded_at.isoformat() if upload is not None else None
                    ),
                    version=(upload.version if upload is not None else None),
                )
            )
        return items

    async def _list_filing_units(
        self,
        *,
        scope: frozenset[UUID] | set[UUID],
    ) -> list[OrgUnit]:
        """Return filing units visible under ``scope``.

        Args:
            scope: :data:`ALL_SCOPES` sentinel or an explicit id set.

        Returns:
            list[OrgUnit]: Filing units, sorted by ``code`` ascending.
        """
        stmt = select(OrgUnit).where(OrgUnit.is_filing_unit.is_(True))
        if scope is not ALL_SCOPES:
            if not scope:
                return []
            stmt = stmt.where(OrgUnit.id.in_(scope))
        stmt = stmt.order_by(OrgUnit.code.asc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _latest_uploads_by_unit(
        self,
        *,
        cycle_id: UUID,
    ) -> dict[UUID, BudgetUpload]:
        """Return the latest :class:`BudgetUpload` per org unit for the cycle.

        Args:
            cycle_id: Target cycle.

        Returns:
            dict[UUID, BudgetUpload]: Latest upload keyed by org unit id.
        """
        stmt = (
            select(BudgetUpload)
            .where(BudgetUpload.cycle_id == cycle_id)
            .order_by(BudgetUpload.version.desc())
        )
        result = await self._db.execute(stmt)
        latest: dict[UUID, BudgetUpload] = {}
        for upload in result.scalars().all():
            # Reason: version desc means the first seen wins per unit id.
            latest.setdefault(upload.org_unit_id, upload)
        return latest

    async def _templates_by_unit(
        self,
        *,
        cycle_id: UUID,
    ) -> dict[UUID, ExcelTemplate]:
        """Return the :class:`ExcelTemplate` row per org unit.

        Args:
            cycle_id: Target cycle.

        Returns:
            dict[UUID, ExcelTemplate]: Templates keyed by org unit id.
        """
        stmt = select(ExcelTemplate).where(ExcelTemplate.cycle_id == cycle_id)
        result = await self._db.execute(stmt)
        return {row.org_unit_id: row for row in result.scalars().all()}

    async def _open_resubmit_ids(
        self,
        *,
        cycle_id: UUID,
    ) -> set[UUID]:
        """Return org_unit_ids with an open :class:`ResubmitRequest`.

        Args:
            cycle_id: Target cycle.

        Returns:
            set[UUID]: Org unit ids with at least one resubmit request.
        """
        stmt = select(ResubmitRequest.org_unit_id).where(ResubmitRequest.cycle_id == cycle_id)
        result = await self._db.execute(stmt)
        return {row[0] for row in result.all()}

    async def _build_summary_response(
        self,
        *,
        cycle_id: UUID,
    ) -> DashboardResponse:
        """Return the CompanyReviewer summary-only payload.

        Args:
            cycle_id: Target cycle id.

        Returns:
            DashboardResponse: ``items=[]`` plus aggregate counters.
        """
        units = await self._list_filing_units(scope=ALL_SCOPES)
        uploads_by_unit = await self._latest_uploads_by_unit(cycle_id=cycle_id)
        total = len(units)
        uploaded = sum(1 for unit in units if unit.id in uploads_by_unit)
        summary = {
            "total_units": total,
            "uploaded": uploaded,
            "pending": max(total - uploaded, 0),
        }
        return DashboardResponse(items=[], summary=summary)

    @staticmethod
    def _apply_filters(
        items: list[DashboardItem],
        filters: DashboardFilters,
    ) -> list[DashboardItem]:
        """Filter / sort / paginate ``items`` according to ``filters``.

        Args:
            items: Unfiltered source rows.
            filters: Caller-provided options.

        Returns:
            list[DashboardItem]: Trimmed result list.
        """
        result = list(items)
        if filters.status is not None:
            result = [row for row in result if row.status == filters.status]
        if filters.org_unit_id is not None:
            result = [row for row in result if row.org_unit_id == filters.org_unit_id]
        if filters.sort == "last_uploaded_at":
            result.sort(
                key=lambda r: (r.last_uploaded_at or ""),
                reverse=True,
            )
        else:
            result.sort(key=lambda r: r.org_unit_name)
        return result[filters.offset : filters.offset + filters.limit]
