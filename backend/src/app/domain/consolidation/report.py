"""Consolidated report builder (FR-015, FR-016).

Joins the latest budget + personnel + shared-cost uploads for a cycle
by ``(org_unit_id, account_code_id)`` and returns a
:class:`ConsolidatedReport` Pydantic payload.

**Required call order** (per spec §4 and CR-013, CR-014, CR-015,
CR-016, CR-036) — do not reorder without updating the unit tests:

1. Resolve the scoped org-unit set (passed in on the
   :class:`ReportScope`).
2. Fetch ``budget_map = get_latest_by_cycle(cycle_id)`` via
   :class:`BudgetUploadService`.
3. Fetch ``personnel_map = get_latest_by_cycle(cycle_id)`` via
   :class:`PersonnelImportService`.
4. Fetch ``shared_cost_map = get_latest_by_cycle(cycle_id)`` via
   :class:`SharedCostImportService`.
5. Load ``ActualExpense`` rows for ``(cycle_id, org_unit_id IN scope)``.
6. Load :class:`OrgUnit` + :class:`AccountCode` rows (names + level).
7. Build one :class:`ConsolidatedReportRow` per
   ``(org_unit_id, account_code_id)`` in the union of all four sources.
8. Compute three per-source ``last_updated_at`` timestamps from the
   latest-version ``uploaded_at`` value per table.
9. Return :class:`ConsolidatedReport`.

Decimal precision: delta_pct is computed via Python :class:`Decimal`
arithmetic with :class:`decimal.ROUND_HALF_UP` to exactly one decimal
place (CR-013). The :meth:`_format_delta_pct` helper returns the
literal string ``"N/A"`` when ``actual`` is ``None`` or zero (CR-014).
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import OrgUnit, User
from app.core.security.rbac import ALL_SCOPES, scoped_org_units
from app.domain.accounts.models import AccountCode, ActualExpense
from app.domain.budget_uploads.models import BudgetUpload
from app.domain.budget_uploads.service import BudgetUploadService
from app.domain.cycles.models import BudgetCycle
from app.domain.personnel.models import PersonnelBudgetUpload
from app.domain.personnel.service import PersonnelImportService
from app.domain.shared_costs.models import SharedCostUpload
from app.domain.shared_costs.service import SharedCostImportService

__all__ = [
    "ConsolidatedReport",
    "ConsolidatedReportRow",
    "ConsolidatedReportService",
    "ExportFormat",
    "ReportScope",
]


_LOG = structlog.get_logger(__name__)


# Reason: architecture §5 and CR-016. ``1000`` is the 處 level; ``0800``,
# ``0500`` and ``0000`` are increasingly higher aggregation levels.
_AGGREGATE_LEVELS: frozenset[str] = frozenset({"1000", "0800", "0500", "0000"})


class ExportFormat(BaseModel):
    """Typed enum wrapper for the export format selection.

    Using a Pydantic wrapper instead of a bare :class:`enum.StrEnum` keeps
    the OpenAPI schema flat while still constraining the value at
    request-parse time.

    Attributes:
        value: Wire value — ``"xlsx"`` or ``"csv"``.
    """

    model_config = ConfigDict(frozen=True)

    value: Literal["xlsx", "csv"] = "xlsx"


class ReportScope(BaseModel):
    """RBAC-resolved scope for a report build call.

    Attributes:
        user_id: UUID of the requesting user (audit + notifications).
        org_unit_ids: Explicit set of permitted org unit UUIDs. An empty
            set means "no scope" (service returns an empty report).
        all_scopes: Sentinel — when ``True``, ``org_unit_ids`` is
            ignored and every org unit is considered in scope.
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    org_unit_ids: frozenset[UUID] = frozenset()
    all_scopes: bool = False


class ConsolidatedReportRow(BaseModel):
    """One row of the consolidated report.

    All monetary fields are :class:`Decimal` (CR-036) and are serialized
    as JSON strings via the class-level ``json_encoders`` config.

    Attributes:
        org_unit_id: Filing unit UUID.
        org_unit_name: Filing unit display name.
        account_code: Account code string (e.g. ``"51010000"``).
        account_name: Account code display name.
        actual: Actual amount from :class:`ActualExpense` (``None`` when
            no row exists).
        operational_budget: Latest-version operational budget amount,
            ``None`` when no upload exists (CR-015).
        personnel_budget: Personnel budget amount, ``None`` below level
            1000 (CR-016).
        shared_cost: Shared cost amount, ``None`` below level 1000
            (CR-016).
        delta_amount: ``operational_budget - actual`` when both are
            known, else ``None``.
        delta_pct: String — one-decimal percent (e.g. ``"9.1"``) or
            literal ``"N/A"`` when ``actual`` is zero or missing
            (CR-013, CR-014).
        budget_status: ``"uploaded"`` or ``"not_uploaded"`` (CR-015).
    """

    model_config = ConfigDict(json_encoders={Decimal: str})

    org_unit_id: UUID
    org_unit_name: str
    account_code: str
    account_name: str
    actual: Decimal | None = None
    operational_budget: Decimal | None = None
    personnel_budget: Decimal | None = None
    shared_cost: Decimal | None = None
    delta_amount: Decimal | None = None
    delta_pct: str = "N/A"
    budget_status: Literal["uploaded", "not_uploaded"] = "not_uploaded"


class ConsolidatedReport(BaseModel):
    """Top-level consolidated report response.

    Attributes:
        cycle_id: UUID of the source cycle.
        rows: Flat list of :class:`ConsolidatedReportRow` values.
        reporting_currency: Cycle's reporting currency (echoed; no
            conversion — CR-036).
        budget_last_updated_at: ``uploaded_at`` of the latest budget
            upload touched, or ``None``.
        personnel_last_updated_at: Latest personnel upload's
            ``uploaded_at`` or ``None``.
        shared_cost_last_updated_at: Latest shared cost upload's
            ``uploaded_at`` or ``None``.
    """

    model_config = ConfigDict(json_encoders={Decimal: str})

    cycle_id: UUID
    rows: list[ConsolidatedReportRow] = []
    reporting_currency: str = "TWD"
    budget_last_updated_at: datetime | None = None
    personnel_last_updated_at: datetime | None = None
    shared_cost_last_updated_at: datetime | None = None


class ConsolidatedReportService:
    """Build :class:`ConsolidatedReport` payloads for a cycle + scope.

    Request-scoped — the service does not hold connection state beyond
    the injected session. Collaborator services are constructed lazily
    from that same session so tests can swap them by assigning to the
    ``_budget``, ``_personnel``, ``_shared`` attributes.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active session.

        Args:
            db: Active :class:`AsyncSession`.
        """
        self._db = db
        self._budget: BudgetUploadService = BudgetUploadService(db)
        self._personnel: PersonnelImportService = PersonnelImportService(db)
        self._shared: SharedCostImportService = SharedCostImportService(db)

    async def resolve_scope(self, *, user: User) -> ReportScope:
        """Return a :class:`ReportScope` derived from the user's RBAC.

        Args:
            user: Authenticated caller.

        Returns:
            ReportScope: Scope object consumable by :meth:`build`.
        """
        scope_set = await scoped_org_units(user, self._db)
        if scope_set is ALL_SCOPES:
            return ReportScope(user_id=user.id, all_scopes=True)
        return ReportScope(user_id=user.id, org_unit_ids=frozenset(scope_set))

    async def build(
        self,
        *,
        cycle_id: UUID,
        scope: ReportScope,
    ) -> ConsolidatedReport:
        """Build the consolidated report for ``cycle_id`` + ``scope``.

        See the module docstring for the exact 9-step call order.

        Args:
            cycle_id: Target cycle UUID.
            scope: RBAC-resolved scope (built by :meth:`resolve_scope`).

        Returns:
            ConsolidatedReport: Populated response payload.
        """
        cycle = await self._db.get(BudgetCycle, cycle_id)
        reporting_currency = cycle.reporting_currency if cycle is not None else "TWD"

        # Step 2-4: fetch the three source maps in declared order.
        budget_map = await self._budget.get_latest_by_cycle(cycle_id)
        personnel_map = await self._personnel.get_latest_by_cycle(cycle_id)
        shared_map = await self._shared.get_latest_by_cycle(cycle_id)

        # Step 5: actuals for the cycle (all org units; scoped below).
        actuals_map = await self._fetch_actuals(cycle_id=cycle_id)

        # Step 6: org unit + account name/level lookups.
        org_units = await self._fetch_org_units(scope=scope)
        units_by_id = {unit.id: unit for unit in org_units}
        account_code_ids = self._collect_account_code_ids(
            budget_map, personnel_map, shared_map, actuals_map
        )
        accounts_by_id = await self._fetch_accounts(account_code_ids)

        # Step 7: compose rows.
        rows: list[ConsolidatedReportRow] = []
        # Reason: union keys across budget, personnel, shared, actual,
        # plus the "no-upload-yet" rows — those are added below via
        # units_without_budget pass so CR-015 always yields a row.
        keys = (
            set(budget_map.keys())
            | set(personnel_map.keys())
            | set(shared_map.keys())
            | set(actuals_map.keys())
        )
        for org_unit_id, account_code_id in sorted(
            keys, key=lambda pair: (str(pair[0]), str(pair[1]))
        ):
            unit = units_by_id.get(org_unit_id)
            account = accounts_by_id.get(account_code_id)
            if unit is None or account is None:
                continue
            if not self._unit_in_scope(unit_id=unit.id, scope=scope):
                continue
            row = self._build_row(
                unit=unit,
                account=account,
                budget_map=budget_map,
                personnel_map=personnel_map,
                shared_map=shared_map,
                actuals_map=actuals_map,
            )
            rows.append(row)

        # CR-015: units with NO budget upload of any kind still need a
        # sentinel row so the caller can distinguish "no upload yet"
        # from "unit excluded from scope". We emit a synthetic row with
        # empty ``account_code`` + ``account_name`` so the display layer
        # knows the row is a unit-level placeholder.
        uploaded_units: set[UUID] = {k[0] for k in budget_map.keys()}
        for unit in org_units:
            if unit.id in uploaded_units:
                continue
            if not self._unit_in_scope(unit_id=unit.id, scope=scope):
                continue
            rows.append(
                ConsolidatedReportRow(
                    org_unit_id=unit.id,
                    org_unit_name=unit.name,
                    account_code="",
                    account_name="",
                    actual=None,
                    operational_budget=None,
                    personnel_budget=None,
                    shared_cost=None,
                    delta_amount=None,
                    delta_pct="N/A",
                    budget_status="not_uploaded",
                )
            )

        # Step 8: the three per-source timestamps.
        budget_ts = await self._latest_budget_ts(cycle_id)
        personnel_ts = await self._latest_personnel_ts(cycle_id)
        shared_ts = await self._latest_shared_ts(cycle_id)

        return ConsolidatedReport(
            cycle_id=cycle_id,
            rows=rows,
            reporting_currency=reporting_currency,
            budget_last_updated_at=budget_ts,
            personnel_last_updated_at=personnel_ts,
            shared_cost_last_updated_at=shared_ts,
        )

    # ================================================================
    #                          internals
    # ================================================================
    def _build_row(
        self,
        *,
        unit: OrgUnit,
        account: AccountCode,
        budget_map: dict[tuple[UUID, UUID], Decimal],
        personnel_map: dict[tuple[UUID, UUID], Decimal],
        shared_map: dict[tuple[UUID, UUID], Decimal],
        actuals_map: dict[tuple[UUID, UUID], Decimal],
    ) -> ConsolidatedReportRow:
        """Construct one :class:`ConsolidatedReportRow`.

        Args:
            unit: Source org unit (provides ``id``, ``name``, ``level_code``).
            account: Source account code (provides ``code`` + ``name``).
            budget_map: Latest operational budget aggregate map.
            personnel_map: Latest personnel aggregate map.
            shared_map: Latest shared cost aggregate map.
            actuals_map: Actual expenses aggregate map.

        Returns:
            ConsolidatedReportRow: Fully populated row with CR-013..016
            semantics applied.
        """
        key = (unit.id, account.id)
        operational_budget = budget_map.get(key)
        actual = actuals_map.get(key)
        include_personnel_shared = unit.level_code in _AGGREGATE_LEVELS
        personnel_budget = personnel_map.get(key) if include_personnel_shared else None
        shared_cost = shared_map.get(key) if include_personnel_shared else None

        if operational_budget is not None and actual is not None:
            delta_amount: Decimal | None = operational_budget - actual
        else:
            delta_amount = None

        delta_pct = self._format_delta_pct(
            delta_amount=delta_amount,
            actual=actual,
        )

        budget_status: Literal["uploaded", "not_uploaded"]
        if operational_budget is None:
            budget_status = "not_uploaded"
        else:
            budget_status = "uploaded"

        return ConsolidatedReportRow(
            org_unit_id=unit.id,
            org_unit_name=unit.name,
            account_code=account.code,
            account_name=account.name,
            actual=actual,
            operational_budget=operational_budget,
            personnel_budget=personnel_budget,
            shared_cost=shared_cost,
            delta_amount=delta_amount,
            delta_pct=delta_pct,
            budget_status=budget_status,
        )

    @staticmethod
    def _format_delta_pct(
        *,
        delta_amount: Decimal | None,
        actual: Decimal | None,
    ) -> str:
        """Return the CR-013 / CR-014 formatted delta-percent string.

        Args:
            delta_amount: ``budget - actual`` or ``None``.
            actual: Actual expense value or ``None``.

        Returns:
            str: Single-decimal percent (e.g. ``"9.1"``) or ``"N/A"``
            when ``actual`` is ``None`` or zero (CR-014).
        """
        if actual is None or actual == 0 or delta_amount is None:
            return "N/A"
        # Reason: CR-013 — quantize to one decimal place with explicit
        # ROUND_HALF_UP so ``100/1100`` renders as ``"9.1"``, not
        # ``"9.0"`` (banker's rounding) or ``"9.09"`` (no quantize).
        ratio = (delta_amount / actual) * Decimal("100")
        quantized = ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return str(quantized)

    @staticmethod
    def _unit_in_scope(
        *,
        unit_id: UUID,
        scope: ReportScope,
    ) -> bool:
        """Return whether ``unit_id`` is permitted under ``scope``.

        Args:
            unit_id: Candidate unit id.
            scope: :class:`ReportScope` instance.

        Returns:
            bool: ``True`` when the caller may see this row.
        """
        if scope.all_scopes:
            return True
        return unit_id in scope.org_unit_ids

    @staticmethod
    def _collect_account_code_ids(
        *maps: dict[tuple[UUID, UUID], Decimal],
    ) -> set[UUID]:
        """Return the union of ``account_code_id`` values across the inputs.

        Args:
            *maps: One or more ``(org_unit_id, account_code_id) →
                Decimal`` maps.

        Returns:
            set[UUID]: Distinct account code ids referenced.
        """
        out: set[UUID] = set()
        for mapping in maps:
            for _unit_id, account_code_id in mapping.keys():
                out.add(account_code_id)
        return out

    async def _fetch_actuals(
        self,
        *,
        cycle_id: UUID,
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """Return the actuals map for ``cycle_id``.

        Args:
            cycle_id: Target cycle id.

        Returns:
            dict[tuple[UUID, UUID], Decimal]: Aggregate map.
        """
        stmt = select(ActualExpense).where(ActualExpense.cycle_id == cycle_id)
        result = await self._db.execute(stmt)
        out: dict[tuple[UUID, UUID], Decimal] = {}
        for row in result.scalars().all():
            key = (row.org_unit_id, row.account_code_id)
            out[key] = out.get(key, Decimal("0")) + row.amount
        return out

    async def _fetch_org_units(
        self,
        *,
        scope: ReportScope,
    ) -> list[OrgUnit]:
        """Return :class:`OrgUnit` rows permitted under ``scope``.

        Args:
            scope: Caller scope.

        Returns:
            list[OrgUnit]: Matching rows (empty when scope is empty).
        """
        stmt = select(OrgUnit)
        if not scope.all_scopes:
            if not scope.org_unit_ids:
                return []
            stmt = stmt.where(OrgUnit.id.in_(scope.org_unit_ids))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_accounts(
        self,
        account_ids: set[UUID],
    ) -> dict[UUID, AccountCode]:
        """Return a ``{id: AccountCode}`` map for ``account_ids``.

        Args:
            account_ids: Ids to resolve.

        Returns:
            dict[UUID, AccountCode]: Lookup map.
        """
        if not account_ids:
            return {}
        stmt = select(AccountCode).where(AccountCode.id.in_(account_ids))
        result = await self._db.execute(stmt)
        return {row.id: row for row in result.scalars().all()}

    async def _latest_budget_ts(self, cycle_id: UUID) -> datetime | None:
        """Return the latest ``BudgetUpload.uploaded_at`` for the cycle.

        Args:
            cycle_id: Target cycle id.

        Returns:
            datetime | None: Latest timestamp or ``None`` when empty.
        """
        stmt = (
            select(BudgetUpload)
            .where(BudgetUpload.cycle_id == cycle_id)
            .order_by(BudgetUpload.version.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.scalars().first()
        return row.uploaded_at if row is not None else None

    async def _latest_personnel_ts(self, cycle_id: UUID) -> datetime | None:
        """Return the latest ``PersonnelBudgetUpload.uploaded_at`` for the cycle.

        Args:
            cycle_id: Target cycle id.

        Returns:
            datetime | None: Latest timestamp or ``None`` when empty.
        """
        stmt = (
            select(PersonnelBudgetUpload)
            .where(PersonnelBudgetUpload.cycle_id == cycle_id)
            .order_by(PersonnelBudgetUpload.version.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.scalars().first()
        return row.uploaded_at if row is not None else None

    async def _latest_shared_ts(self, cycle_id: UUID) -> datetime | None:
        """Return the latest ``SharedCostUpload.uploaded_at`` for the cycle.

        Args:
            cycle_id: Target cycle id.

        Returns:
            datetime | None: Latest timestamp or ``None`` when empty.
        """
        stmt = (
            select(SharedCostUpload)
            .where(SharedCostUpload.cycle_id == cycle_id)
            .order_by(SharedCostUpload.version.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.scalars().first()
        return row.uploaded_at if row is not None else None
