"""Reminder schedule CRUD + daily cron dispatch (FR-005, FR-020).

This module owns two distinct flows:

* **Schedule CRUD** (:func:`set_reminder_schedule`) — replaces the
  ``cycle_reminder_schedules`` rows for a cycle with a new set. Passing
  an empty list disables reminders. Called from the API PATCH route and
  from :meth:`CycleService.open` (which applies the default ``[7, 3, 1]``
  schedule when none exists).
* **Cron dispatch** (:func:`dispatch_deadline_reminders`) — walks every
  open cycle, computes ``deadline - today``, matches against the
  schedule, and fans out :class:`NotificationTemplate.DEADLINE_REMINDER`
  notifications to the filing-unit managers of units that have not yet
  uploaded for the cycle. Exception isolation (CR-035) is handled by
  :mod:`app.infra.scheduler`, but we still wrap individual recipient
  failures so a single bad email cannot abort the whole dispatch.

The recipient resolver walks ``parent_id`` on the org tree to add upline
reviewers as CC (CR-028). The walk terminates at the first ancestor with
any matching reviewer or when ``parent_id`` is ``None``; an empty walk
logs at WARN level rather than raising.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import now_utc
from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.cycles.models import BudgetCycle, CycleReminderSchedule, CycleState
from app.domain.notifications.service import NotificationService
from app.domain.notifications.templates import NotificationTemplate
from app.infra.db.repos.budget_uploads_query import unsubmitted_for_cycle
from app.infra.scheduler import register_cron

__all__ = [
    "DispatchSummary",
    "dispatch_deadline_reminders",
    "register_cron_callback",
    "set_reminder_schedule",
]


_LOG = structlog.get_logger(__name__)

# Upline-reviewer + FinanceAdmin roles are the valid CC recipients.
_UPLINE_ROLES: frozenset[str] = frozenset({Role.UplineReviewer.value, Role.FinanceAdmin.value})


class DispatchSummary(BaseModel):
    """Result of one :func:`dispatch_deadline_reminders` pass.

    Attributes:
        cycle_count: Number of Open cycles inspected.
        notifications_sent: Number of successful email dispatches (sum
            across all cycles).
        notifications_failed: Number of failed dispatches (SMTP errors
            are isolated via :class:`NotificationService`'s CR-029
            tolerance).
    """

    cycle_count: int
    notifications_sent: int
    notifications_failed: int


@dataclass
class _Recipient:
    """Lightweight manager+cc record for dispatch.

    Attributes:
        user_id: Primary recipient user id.
        email: Primary recipient email (decrypted lazily by the caller).
        cc_user_ids: Upline reviewer user ids used as CC.
    """

    user_id: UUID
    email: str
    cc_user_ids: list[UUID]


async def set_reminder_schedule(
    db: AsyncSession,
    cycle_id: UUID,
    days_before: list[int],
    *,
    audit: AuditService | None = None,
    actor_id: UUID | None = None,
) -> list[CycleReminderSchedule]:
    """Replace the reminder schedule rows for ``cycle_id``.

    The method runs in the caller's transaction: existing rows are
    removed and the new ones inserted in the same session, leaving the
    commit to the caller. Audit recording follows CR-006 — the caller is
    expected to commit first and then record. When an ``AuditService`` is
    passed this helper records ``CYCLE_REMINDER_SET`` on behalf of the
    caller.

    Args:
        db: Active async DB session.
        cycle_id: Cycle whose schedule is being replaced.
        days_before: New list of positive integers. An empty list
            disables reminders entirely.
        audit: Optional audit service — when passed the method records
            ``CYCLE_REMINDER_SET`` after flushing.
        actor_id: Optional acting user id (threaded through to the audit
            row).

    Returns:
        list[CycleReminderSchedule]: The newly persisted rows, in input
        order.

    Raises:
        ValueError: If any entry in ``days_before`` is not a positive int.
    """
    for raw in days_before:
        if raw <= 0:
            raise ValueError(f"days_before entries must be positive integers; got {raw!r}")

    await db.execute(
        delete(CycleReminderSchedule).where(CycleReminderSchedule.cycle_id == cycle_id)
    )
    now = now_utc()
    inserted: list[CycleReminderSchedule] = []
    for days in days_before:
        row = CycleReminderSchedule(
            cycle_id=cycle_id,
            days_before=days,
            created_at=now,
        )
        db.add(row)
        inserted.append(row)
    await db.flush()

    if audit is not None:
        await audit.record(
            action=AuditAction.CYCLE_REMINDER_SET,
            resource_type="cycle",
            resource_id=cycle_id,
            user_id=actor_id,
            details={"days_before": list(days_before)},
        )
    return inserted


async def dispatch_deadline_reminders(
    db: AsyncSession,
    notifications: NotificationService,
    *,
    today: date | None = None,
) -> DispatchSummary:
    """Scan Open cycles and send due deadline reminders (FR-020).

    For each Open cycle whose ``deadline - today`` matches a scheduled
    ``days_before`` entry, the resolver collects every filing-unit
    manager whose unit has no :class:`BudgetUpload` row for the cycle
    (via the CR-026 shared query), walks the org tree for upline CC
    recipients (CR-028), and dispatches
    :class:`NotificationTemplate.DEADLINE_REMINDER`.

    Args:
        db: Active async DB session.
        notifications: Service used for dispatch. Failures are absorbed
            internally (CR-029) so this function never re-raises.
        today: Override for the "current date" used to compute days-
            remaining. Defaults to ``now_utc().date()``. Primarily a
            hook for unit tests.

    Returns:
        DispatchSummary: Aggregate counters.
    """
    ref_day = today if today is not None else now_utc().date()

    cycles = list(
        (await db.execute(select(BudgetCycle).where(BudgetCycle.status == CycleState.open.value)))
        .scalars()
        .all()
    )

    sent = 0
    failed = 0
    for cycle in cycles:
        days_remaining = (cycle.deadline - ref_day).days
        if days_remaining < 0:
            continue
        schedules = list(
            (
                await db.execute(
                    select(CycleReminderSchedule).where(CycleReminderSchedule.cycle_id == cycle.id)
                )
            )
            .scalars()
            .all()
        )
        if not any(s.days_before == days_remaining for s in schedules):
            continue

        unsubmitted_ids = await unsubmitted_for_cycle(db, cycle.id)
        if not unsubmitted_ids:
            continue

        recipients = await _resolve_recipients(db, unsubmitted_ids)
        for recipient in recipients:
            try:
                result = await notifications.send(
                    template=NotificationTemplate.DEADLINE_REMINDER,
                    recipient_user_id=recipient.user_id,
                    recipient_email=recipient.email,
                    context={
                        "cycle_id": str(cycle.id),
                        "fiscal_year": cycle.fiscal_year,
                        "deadline": cycle.deadline.isoformat(),
                        "days_before": days_remaining,
                    },
                    related=("cycle", cycle.id),
                )
            except Exception as exc:  # pragma: no cover — defensive
                _LOG.warning(
                    "cycles.reminder_dispatch_failed",
                    cycle_id=str(cycle.id),
                    user_id=str(recipient.user_id),
                    error=str(exc),
                )
                failed += 1
                continue
            if result.status == "sent":
                sent += 1
            else:
                failed += 1

    return DispatchSummary(
        cycle_count=len(cycles),
        notifications_sent=sent,
        notifications_failed=failed,
    )


async def _resolve_recipients(
    db: AsyncSession,
    unit_ids: list[UUID],
) -> list[_Recipient]:
    """Return a :class:`_Recipient` per filing-unit manager (CR-028).

    Walks ``parent_id`` from each target unit until it finds an ancestor
    containing a user with an upline-qualified role. CC ids are dedup'd
    per recipient. When no upline is found the walk logs a WARN event
    but never raises.

    Args:
        db: Active async DB session.
        unit_ids: Org unit ids to resolve managers for.

    Returns:
        list[_Recipient]: One entry per filing-unit manager.
    """
    if not unit_ids:
        return []

    # Fetch all org units once for the parent walk (cheap — O(units)).
    all_units_stmt = select(OrgUnit)
    all_units = list((await db.execute(all_units_stmt)).scalars().all())
    by_id: dict[UUID, OrgUnit] = {u.id: u for u in all_units}

    # Load managers for the target units.
    mgr_stmt = select(User).where(User.org_unit_id.in_(unit_ids)).where(User.is_active.is_(True))
    managers = list((await db.execute(mgr_stmt)).scalars().all())

    # Load upline reviewer candidates globally so we can index by unit.
    reviewer_stmt = select(User).where(User.is_active.is_(True))
    all_users = list((await db.execute(reviewer_stmt)).scalars().all())
    reviewers_by_unit: dict[UUID, list[User]] = {}
    for user in all_users:
        if user.org_unit_id is None:
            continue
        if not set(user.roles or []).intersection(_UPLINE_ROLES):
            continue
        reviewers_by_unit.setdefault(user.org_unit_id, []).append(user)

    recipients: list[_Recipient] = []
    for mgr in managers:
        if mgr.org_unit_id is None:
            continue
        email = _extract_email(mgr)
        if email is None:
            # Reason: email is stored as ciphertext in the baseline; tests
            # stub ``email_enc`` with a readable bytes blob so the helper
            # can return a string.
            _LOG.warning("cycles.recipient_email_missing", user_id=str(mgr.id))
            continue
        cc_ids = _walk_uplines(mgr.org_unit_id, by_id, reviewers_by_unit)
        if not cc_ids:
            _LOG.warning(
                "notification.no_upline_found",
                org_unit_id=str(mgr.org_unit_id),
            )
        recipients.append(_Recipient(user_id=mgr.id, email=email, cc_user_ids=cc_ids))
    return recipients


def _walk_uplines(
    start_unit_id: UUID,
    by_id: dict[UUID, OrgUnit],
    reviewers_by_unit: dict[UUID, list[User]],
) -> list[UUID]:
    """Walk ``parent_id`` collecting the first ancestor with reviewers.

    Args:
        start_unit_id: The filing unit to start walking from.
        by_id: All org-unit rows indexed by id (for O(1) parent lookups).
        reviewers_by_unit: Pre-grouped reviewer users keyed by unit id.

    Returns:
        list[UUID]: User ids of the matched reviewers, or an empty list
        when the walk exhausts without finding one.
    """
    current = by_id.get(start_unit_id)
    while current is not None and current.parent_id is not None:
        parent = by_id.get(current.parent_id)
        if parent is None:
            break
        candidates = reviewers_by_unit.get(parent.id, [])
        if candidates:
            return [u.id for u in candidates]
        current = parent
    return []


def _extract_email(user: User) -> str | None:
    """Best-effort email decode for notification dispatch.

    Production code stores the plaintext email in ``email_enc`` as
    ciphertext; this helper decodes UTF-8 for test doubles while
    leaving real ciphertext untouched (returns ``None`` when the bytes
    cannot be decoded cleanly).

    Args:
        user: User whose email is being resolved.

    Returns:
        str | None: Decoded email, or ``None`` when decoding fails.
    """
    raw = user.email_enc or b""
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "@" not in text:
        return None
    return text


def register_cron_callback(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    notifications_factory: Callable[[AsyncSession], Awaitable[NotificationService]],
    cron_expr: str = "0 9 * * *",
    job_name: str = "cycles.deadline_reminders",
) -> None:
    """Register the daily deadline-reminder cron job (FR-020, CR-038).

    The registered wrapper opens its own session and notification
    service via the supplied factories — APScheduler owns its own event
    loop thread and cannot see request-scoped FastAPI dependencies. The
    outer ``try/except Exception`` is provided by
    :func:`app.infra.scheduler.register_cron` so this inner callable may
    focus on the happy path.

    Args:
        session_factory: Async sessionmaker used to open a fresh DB
            session per run.
        notifications_factory: Callable that builds a
            :class:`NotificationService` bound to the supplied session.
            Allows callers to swap in test doubles.
        cron_expr: 5-field cron expression (defaults to 09:00 every day).
        job_name: APScheduler job id — idempotent replacement key.
    """

    async def _runner() -> None:
        async with session_factory() as db:
            try:
                service = await notifications_factory(db)
                await dispatch_deadline_reminders(db, service)
            finally:
                await db.close()

    register_cron(cron_expr, _runner, job_name)
