"""High-level :class:`CycleService` — the public facade of ``domain.cycles``.

The service is the single entry point for every cycle lifecycle
operation (FR-001..FR-006) and owns **CR-005** via the
:meth:`assert_open` method that downstream importers (Batch 5) call as
their first action. Each state-mutating method follows **CR-006**
(commit the domain change, then record the audit row). The module also
exposes :meth:`set_exclusions` — the tiny helper the admin org-units
PATCH / exclude routes call when they need to mutate
``OrgUnit.excluded_for_cycle_ids`` as part of the FR-002 exclusion flow.

``CycleService`` is constructed with only an :class:`AsyncSession`. The
signature matches the Batch 3 lazy-import call site in
:mod:`app.domain.accounts.service`:

    service = CycleService(db)
    await service.assert_open(cycle_id)

which means :meth:`assert_open` takes just the cycle id and reuses the
session stored on the instance.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.cycles.exclusions import apply_exclusion, validate_currency
from app.domain.cycles.filing_units import FilingUnitInfo, list_filing_units
from app.domain.cycles.models import BudgetCycle, CycleReminderSchedule, CycleState
from app.domain.cycles.reminders import (
    DispatchSummary,
    dispatch_deadline_reminders,
    set_reminder_schedule,
)
from app.domain.cycles.state_machine import assert_transition
from app.domain.notifications.service import NotificationService

__all__ = ["CycleService", "DispatchSummary", "FilingUnitInfo"]


_DEFAULT_REMINDER_DAYS: tuple[int, ...] = (7, 3, 1)


class CycleService:
    """Write + read facade for :class:`BudgetCycle` and its satellites.

    The service is request-scoped — callers build one instance per
    session and call the methods directly. ``AuditService`` is
    constructed on the same session so that the audit write participates
    in the caller's transaction boundary (CR-006).
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active session.

        Args:
            db: Active :class:`AsyncSession`.
        """
        self._db = db
        self._audit = AuditService(db)

    # ------------------------------------------------------------------ reads
    async def get(self, cycle_id: UUID) -> BudgetCycle:
        """Fetch a :class:`BudgetCycle` by id.

        Args:
            cycle_id: Target cycle id.

        Returns:
            BudgetCycle: ORM row.

        Raises:
            NotFoundError: ``CYCLE_001`` when no row matches. The
                registered ``CYCLE_001`` code is re-used rather than
                adding a new ``CYCLE_NOT_FOUND`` entry — the error
                message differentiates the case for the caller.
        """
        row = await self._db.get(BudgetCycle, cycle_id)
        if row is None:
            raise NotFoundError(
                "CYCLE_001",
                f"Cycle {cycle_id} not found",
            )
        return row

    async def get_status(self, cycle_id: UUID) -> CycleState:
        """Return the current status enum value for a cycle.

        Args:
            cycle_id: Target cycle id.

        Returns:
            CycleState: Parsed status value.
        """
        cycle = await self.get(cycle_id)
        return CycleState(cycle.status)

    async def list(self, *, fiscal_year: int | None = None) -> list[BudgetCycle]:
        """Return every cycle, newest-first.

        Args:
            fiscal_year: Optional filter.

        Returns:
            list[BudgetCycle]: Matching rows ordered by ``fiscal_year``
            descending.
        """
        stmt = select(BudgetCycle).order_by(
            BudgetCycle.fiscal_year.desc(), BudgetCycle.created_at.desc()
        )
        if fiscal_year is not None:
            stmt = stmt.where(BudgetCycle.fiscal_year == fiscal_year)
        return list((await self._db.execute(stmt)).scalars().all())

    async def list_filing_units(self, cycle_id: UUID) -> list[FilingUnitInfo]:
        """Return filing-unit info rows for a cycle.

        Thin wrapper around :func:`app.domain.cycles.filing_units.list_filing_units`.

        Args:
            cycle_id: Target cycle id.

        Returns:
            list[FilingUnitInfo]: All filing units (CR-008).
        """
        return await list_filing_units(self._db, cycle_id)

    # ------------------------------------------------------------- assert_open
    async def assert_open(self, cycle_id: UUID) -> None:
        """Raise ``CYCLE_004`` if the cycle is not in :class:`CycleState.open`.

        CR-005 contract: every M4/M5/M6 importer calls this as its first
        action. The signature intentionally takes only ``cycle_id`` so
        the Batch 3 lazy-import call site in
        :class:`app.domain.accounts.service.AccountService._assert_cycle_open`
        keeps working without changes.

        Args:
            cycle_id: Target cycle id.

        Raises:
            NotFoundError: ``CYCLE_001`` when no row matches.
            AppError: ``CYCLE_004`` when the cycle is not Open.
        """
        cycle = await self.get(cycle_id)
        if cycle.status != CycleState.open.value:
            raise AppError(
                "CYCLE_004",
                f"Cycle {cycle_id} is not open (status={cycle.status})",
            )

    # ------------------------------------------------------------------ create
    async def create(
        self,
        *,
        fiscal_year: int,
        deadline: date,
        reporting_currency: str,
        user: User,
    ) -> BudgetCycle:
        """Insert a new Draft :class:`BudgetCycle` (FR-001).

        Enforces the CR-023 currency contract (validated as a 3-letter
        uppercase ISO 4217 code; stored as-is). Raises ``CYCLE_001``
        when a non-closed cycle already exists for the target fiscal
        year — the baseline migration ships a partial UNIQUE index on
        ``(fiscal_year) WHERE status != 'closed'`` which would also
        raise, but the explicit pre-check yields a nicer error.

        Args:
            fiscal_year: Four-digit year.
            deadline: Submission deadline date.
            reporting_currency: 3-letter ISO 4217 currency code.
            user: Creator.

        Returns:
            BudgetCycle: The newly persisted Draft row.

        Raises:
            ConflictError: ``CYCLE_001`` on duplicate active year.
            ValueError: When ``reporting_currency`` is malformed.
        """
        currency = validate_currency(reporting_currency)

        existing_stmt = (
            select(BudgetCycle)
            .where(BudgetCycle.fiscal_year == fiscal_year)
            .where(BudgetCycle.status != CycleState.closed.value)
        )
        existing = (await self._db.execute(existing_stmt)).scalars().first()
        if existing is not None:
            raise ConflictError(
                "CYCLE_001",
                f"A non-closed cycle already exists for fiscal year {fiscal_year}",
            )

        now = now_utc()
        cycle = BudgetCycle(
            fiscal_year=fiscal_year,
            deadline=deadline,
            reporting_currency=currency,
            status=CycleState.draft.value,
            created_by=user.id,
            created_at=now,
            updated_at=now,
        )
        self._db.add(cycle)
        await self._db.commit()

        await self._audit.record(
            action=AuditAction.CYCLE_CREATE,
            resource_type="cycle",
            resource_id=cycle.id,
            user_id=user.id,
            details={
                "fiscal_year": fiscal_year,
                "deadline": deadline.isoformat(),
                "reporting_currency": currency,
            },
        )
        await self._db.commit()
        return cycle

    # -------------------------------------------------------------------- open
    async def open(
        self,
        cycle_id: UUID,
        user: User,
    ) -> tuple[BudgetCycle, list[OrgUnit]]:
        """Transition ``cycle_id`` from Draft to Open (FR-003).

        CR-008 sequencing: enumerate every filing unit first, then check
        ``has_manager == False AND not excluded`` as the block condition.
        Missing-manager failures are collected into a single
        ``CYCLE_002`` raise so the operator sees every offending unit in
        one pass. Raises ``CYCLE_003`` when the cycle is not Draft.

        On success the default reminder schedule (``[7, 3, 1]``) is
        applied when none exists (FR-005 "default-on" decision).

        Args:
            cycle_id: Target cycle id.
            user: Actor performing the open.

        Returns:
            tuple[BudgetCycle, list[OrgUnit]]: Updated cycle and the
            list of non-excluded filing units (consumed by the
            orchestrator in Batch 6 for template generation).

        Raises:
            ConflictError: ``CYCLE_002`` missing manager, ``CYCLE_003``
                wrong state.
            NotFoundError: ``CYCLE_001`` when the cycle does not exist.
        """
        cycle = await self.get(cycle_id)
        current = CycleState(cycle.status)
        assert_transition(current, CycleState.open)

        infos = await list_filing_units(self._db, cycle_id)
        missing = [info for info in infos if not info.has_manager and not info.excluded]
        if missing:
            missing_codes = sorted(info.code for info in missing)
            raise ConflictError(
                "CYCLE_002",
                f"Filing units missing a manager: {', '.join(missing_codes)}",
                details=[{"code": info.code, "name": info.name} for info in missing],
            )

        now = now_utc()
        cycle.status = CycleState.open.value
        cycle.opened_at = now
        cycle.updated_at = now

        existing_schedule = (
            (
                await self._db.execute(
                    select(CycleReminderSchedule).where(CycleReminderSchedule.cycle_id == cycle.id)
                )
            )
            .scalars()
            .first()
        )
        if existing_schedule is None:
            await set_reminder_schedule(self._db, cycle.id, list(_DEFAULT_REMINDER_DAYS))

        await self._db.commit()

        await self._audit.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            resource_id=cycle.id,
            user_id=user.id,
            details={
                "fiscal_year": cycle.fiscal_year,
                "deadline": cycle.deadline.isoformat(),
                "filing_units": [info.code for info in infos if not info.excluded],
            },
        )
        await self._db.commit()

        # Reason: reload each OrgUnit cleanly so downstream orchestrator
        # code gets full ORM rows (not the short projection exposed by
        # FilingUnitInfo).
        actionable_unit_ids = [info.org_unit_id for info in infos if not info.excluded]
        if not actionable_unit_ids:
            return cycle, []
        units_stmt = (
            select(OrgUnit).where(OrgUnit.id.in_(actionable_unit_ids)).order_by(OrgUnit.code.asc())
        )
        actionable_units = list((await self._db.execute(units_stmt)).scalars().all())
        return cycle, actionable_units

    # ------------------------------------------------------------------- close
    async def close(self, cycle_id: UUID, user: User) -> BudgetCycle:
        """Transition an Open cycle to Closed (FR-006).

        Args:
            cycle_id: Target cycle id.
            user: Actor performing the close.

        Returns:
            BudgetCycle: The updated row.

        Raises:
            ConflictError: ``CYCLE_003`` when the cycle is not Open.
            NotFoundError: ``CYCLE_001`` when missing.
        """
        cycle = await self.get(cycle_id)
        assert_transition(CycleState(cycle.status), CycleState.closed)
        now = now_utc()
        cycle.status = CycleState.closed.value
        cycle.closed_at = now
        cycle.closed_by = user.id
        cycle.updated_at = now
        await self._db.commit()

        await self._audit.record(
            action=AuditAction.CYCLE_CLOSE,
            resource_type="cycle",
            resource_id=cycle.id,
            user_id=user.id,
            details={"fiscal_year": cycle.fiscal_year},
        )
        await self._db.commit()
        return cycle

    # ------------------------------------------------------------------ reopen
    async def reopen(
        self,
        cycle_id: UUID,
        reason: str,
        user: User,
    ) -> BudgetCycle:
        """Reopen a Closed cycle within the reopen window (CR-037).

        SystemAdmin only — the route layer enforces this via
        :func:`require_role`, and we re-check on the service instance as
        a defensive measure. ``closed_at`` is the reference timestamp
        (never ``created_at`` or ``updated_at``) per CR-037.

        Args:
            cycle_id: Target cycle id.
            reason: Operator justification (stored on the row +
                audit details).
            user: Actor — must carry SystemAdmin.

        Returns:
            BudgetCycle: The reopened row with status=open.

        Raises:
            ConflictError: ``CYCLE_003`` wrong state.
            AppError: ``CYCLE_005`` window elapsed.
        """
        if Role.SystemAdmin not in user.role_set():
            raise AppError(
                "RBAC_001",
                "Only SystemAdmin may reopen a cycle",
            )
        cycle = await self.get(cycle_id)
        if CycleState(cycle.status) != CycleState.closed:
            assert_transition(CycleState(cycle.status), CycleState.open)

        window_days = get_settings().reopen_window_days
        if cycle.closed_at is None:
            raise AppError(
                "CYCLE_005",
                "Cycle closed_at is null; reopen window cannot be verified",
            )
        elapsed_days = (now_utc() - cycle.closed_at).days
        if elapsed_days > window_days:
            raise AppError(
                "CYCLE_005",
                f"Reopen window elapsed ({elapsed_days}d > {window_days}d)",
            )

        now = now_utc()
        cycle.status = CycleState.open.value
        cycle.reopen_reason = reason
        cycle.reopened_at = now
        cycle.updated_at = now
        await self._db.commit()

        await self._audit.record(
            action=AuditAction.CYCLE_REOPEN,
            resource_type="cycle",
            resource_id=cycle.id,
            user_id=user.id,
            details={"reason": reason, "elapsed_days": elapsed_days},
        )
        await self._db.commit()
        return cycle

    # ------------------------------------------------------------ reminders
    async def set_reminder_schedule(
        self,
        cycle_id: UUID,
        days_before: list[int],
        user: User,
    ) -> list[CycleReminderSchedule]:
        """Replace the reminder schedule for a cycle (FR-005).

        Args:
            cycle_id: Target cycle id.
            days_before: New schedule; an empty list disables reminders.
            user: Actor (threaded into the audit row).

        Returns:
            list[CycleReminderSchedule]: Persisted rows.
        """
        rows = await set_reminder_schedule(self._db, cycle_id, days_before)
        await self._db.commit()
        await self._audit.record(
            action=AuditAction.CYCLE_REMINDER_SET,
            resource_type="cycle",
            resource_id=cycle_id,
            user_id=user.id,
            details={"days_before": list(days_before)},
        )
        await self._db.commit()
        return rows

    async def dispatch_deadline_reminders(
        self,
        notifications: NotificationService,
    ) -> DispatchSummary:
        """Thin wrapper around :func:`reminders.dispatch_deadline_reminders`.

        Args:
            notifications: Service used for SMTP dispatch.

        Returns:
            DispatchSummary: Aggregate counters.
        """
        return await dispatch_deadline_reminders(self._db, notifications)

    # ------------------------------------------------------------ exclusions
    async def set_exclusions(
        self,
        *,
        org_unit_id: UUID,
        cycle_id: UUID,
        excluded: bool,
        user: User,
    ) -> OrgUnit:
        """Toggle ``cycle_id`` on/off the unit's ``excluded_for_cycle_ids``.

        Thin wrapper around :func:`app.domain.cycles.exclusions.apply_exclusion`.

        Args:
            org_unit_id: Target org unit id.
            cycle_id: Cycle id.
            excluded: ``True`` to add the cycle id; ``False`` to remove.
            user: Acting admin.

        Returns:
            OrgUnit: Updated org unit row.
        """
        return await apply_exclusion(
            self._db,
            self._audit,
            org_unit_id=org_unit_id,
            cycle_id=cycle_id,
            excluded=excluded,
            user=user,
        )
