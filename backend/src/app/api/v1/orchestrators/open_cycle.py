"""Open-cycle orchestrator (FR-003 5-step pipeline).

Single entry point for transitioning a :class:`BudgetCycle` from
``Draft`` to ``Open``. Call order is fixed and mandated by CR-005,
CR-008, CR-009, CR-010:

1. **RBAC** — ``FinanceAdmin`` or ``SystemAdmin`` only. Enforced at the
   route layer via ``Depends(require_role(...))`` and re-checked in the
   orchestrator body as a defence-in-depth measure.
2. **CycleService.open** — performs the state transition, audits
   ``CYCLE_OPEN``, and returns the actionable :class:`OrgUnit` list
   (excludes ``0000公司`` and units whose ``excluded_for_cycle_ids``
   contains the target cycle).
3. **TemplateService.generate_for_cycle** — per-unit fault isolation.
   Each unit's success or error is returned as
   :class:`TemplateGenerationResult`.
4. **NotificationService.send_batch** — fans out
   :class:`NotificationTemplate.CYCLE_OPENED` to the managers of every
   successfully-generated filing unit. Step 4 failures are non-fatal:
   dispatch errors are recorded in the returned
   :class:`DispatchSummary`.
5. **Return** :class:`OpenCycleResponse`.

Any CYCLE_002 / CYCLE_003 raised inside step 2 propagates unchanged to
the global exception handler (409 to the caller).
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError
from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.cycles.models import BudgetCycle
from app.domain.cycles.service import CycleService
from app.domain.notifications.service import NotificationService
from app.domain.notifications.templates import NotificationTemplate
from app.domain.templates.service import TemplateGenerationResult, TemplateService
from app.infra.db.session import get_session

__all__ = [
    "DispatchSummary",
    "GenerationSummary",
    "OpenCycleResponse",
    "open_cycle_endpoint",
    "router",
]


_LOG = structlog.get_logger(__name__)


router = APIRouter(prefix="/cycles", tags=["orchestrators"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class GenerationSummary(BaseModel):
    """Aggregate generation result.

    Attributes:
        total: Number of filing units attempted.
        generated: Number of units whose workbook was persisted.
        errors: Number of per-unit failures.
        error_details: One dict per failing unit.
    """

    model_config = ConfigDict(frozen=True)

    total: int
    generated: int
    errors: int
    error_details: list[dict[str, str]] = []


class DispatchSummary(BaseModel):
    """Aggregate notification dispatch result.

    Attributes:
        total_recipients: Count of unique ``(user_id, email)`` pairs.
        sent: Number of successful SMTP dispatches.
        errors: Number of failed SMTP dispatches.
    """

    model_config = ConfigDict(frozen=True)

    total_recipients: int
    sent: int
    errors: int


class CycleSnapshot(BaseModel):
    """Minimal serialized :class:`BudgetCycle` for the response.

    Attributes:
        id: Cycle id.
        fiscal_year: Fiscal year.
        status: Current cycle status (post-transition).
        reporting_currency: Echoed reporting currency.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fiscal_year: int
    status: str
    reporting_currency: str


class OpenCycleResponse(BaseModel):
    """Aggregated response body for the open-cycle endpoint.

    Attributes:
        cycle: Serialized cycle snapshot after the transition.
        transition: ``"draft_to_open"`` on success.
        generation_summary: Template generation outcome.
        dispatch_summary: Notification dispatch outcome.
    """

    cycle: CycleSnapshot
    transition: str = "draft_to_open"
    generation_summary: GenerationSummary
    dispatch_summary: DispatchSummary


# ---------------------------------------------------------------------------
# Orchestrator body
# ---------------------------------------------------------------------------
async def open_cycle(
    *,
    session: AsyncSession,
    cycle_id: UUID,
    user: User,
    cycle_service: CycleService | None = None,
    template_service: TemplateService | None = None,
    notification_service: NotificationService | None = None,
) -> OpenCycleResponse:
    """Execute the 5-step open-cycle pipeline.

    The service instances are resolved lazily from ``session`` when not
    injected so the same function can be driven directly from tests.

    Args:
        session: Active async session.
        cycle_id: Target cycle id.
        user: Acting user (must carry FinanceAdmin or SystemAdmin).
        cycle_service: Optional injected :class:`CycleService`.
        template_service: Optional injected :class:`TemplateService`.
        notification_service: Optional injected
            :class:`NotificationService`. When ``None``, Step 4 still
            runs but produces an empty dispatch summary.

    Returns:
        OpenCycleResponse: Aggregated outcome.

    Raises:
        ForbiddenError: ``RBAC_001`` if the acting user lacks the
            required role.
        AppError: Propagated from :meth:`CycleService.open`
            (``CYCLE_002``, ``CYCLE_003``).
    """
    # Step 1 — Defensive RBAC re-check.
    allowed = {Role.FinanceAdmin, Role.SystemAdmin}
    if not user.role_set().intersection(allowed):
        raise ForbiddenError(
            "RBAC_001",
            "open_cycle requires FinanceAdmin or SystemAdmin",
        )

    cycle_svc = cycle_service if cycle_service is not None else CycleService(session)
    template_svc = template_service if template_service is not None else TemplateService(session)

    # Step 2 — Transition and resolve actionable filing units (CR-008).
    cycle, filing_units = await cycle_svc.open(cycle_id, user)

    # Step 3 — Per-unit generation (fault-isolated).
    generation_results: list[TemplateGenerationResult] = await template_svc.generate_for_cycle(
        cycle=cycle,
        filing_units=filing_units,
        user=user,
    )

    generation_summary = _summarize_generation(generation_results)

    # Step 4 — Fan out CYCLE_OPENED notifications to managers of
    # successfully-generated units.
    generated_unit_ids: set[UUID] = {
        result.org_unit_id for result in generation_results if result.status == "generated"
    }
    recipients = await _resolve_recipients(
        session=session,
        filing_units=filing_units,
        generated_unit_ids=generated_unit_ids,
    )
    dispatch_summary = await _send_cycle_opened(
        notification_service=notification_service,
        recipients=recipients,
        cycle=cycle,
    )

    # Step 5 — Assemble response.
    return OpenCycleResponse(
        cycle=CycleSnapshot(
            id=cycle.id,
            fiscal_year=cycle.fiscal_year,
            status=cycle.status,
            reporting_currency=cycle.reporting_currency,
        ),
        transition="draft_to_open",
        generation_summary=generation_summary,
        dispatch_summary=dispatch_summary,
    )


def _summarize_generation(
    results: list[TemplateGenerationResult],
) -> GenerationSummary:
    """Fold ``results`` into a :class:`GenerationSummary`.

    Args:
        results: Per-unit generation results.

    Returns:
        GenerationSummary: Aggregated counters.
    """
    total = len(results)
    generated = sum(1 for r in results if r.status == "generated")
    errors = total - generated
    error_details = [
        {"org_unit_id": str(r.org_unit_id), "error": r.error or ""}
        for r in results
        if r.status != "generated"
    ]
    return GenerationSummary(
        total=total,
        generated=generated,
        errors=errors,
        error_details=error_details,
    )


async def _resolve_recipients(
    *,
    session: AsyncSession,
    filing_units: list,  # type: ignore[type-arg]
    generated_unit_ids: set[UUID],
) -> list[tuple[UUID, str]]:
    """Return ``(user_id, email)`` recipient tuples for notifications.

    Looks up every active user whose ``org_unit_id`` matches a
    successfully-generated filing unit. The email is decoded from
    ``email_enc``; rows with non-decodable bytes are skipped with a
    WARN log.

    Args:
        session: Active async session.
        filing_units: :class:`OrgUnit` rows from Step 2.
        generated_unit_ids: Subset of unit ids with successful
            generation (recipients of units that failed generation are
            skipped).

    Returns:
        list[tuple[UUID, str]]: Recipients suitable for
        :meth:`NotificationService.send_batch`.
    """
    if not generated_unit_ids:
        return []
    target_ids = {unit.id for unit in filing_units if unit.id in generated_unit_ids}
    if not target_ids:
        return []

    stmt = select(User).where(
        User.org_unit_id.in_(target_ids),
        User.is_active.is_(True),
    )
    result = await session.execute(stmt)
    users = list(result.scalars().all())

    recipients: list[tuple[UUID, str]] = []
    for user in users:
        raw = user.email_enc or b""
        if not raw:
            continue
        try:
            email = raw.decode("utf-8")
        except UnicodeDecodeError:
            _LOG.warning("open_cycle.bad_email_enc", user_id=str(user.id))
            continue
        if "@" not in email:
            continue
        recipients.append((user.id, email))
    return recipients


async def _send_cycle_opened(
    *,
    notification_service: NotificationService | None,
    recipients: list[tuple[UUID, str]],
    cycle: BudgetCycle,
) -> DispatchSummary:
    """Dispatch :data:`NotificationTemplate.CYCLE_OPENED` best-effort.

    Args:
        notification_service: Optional injected service. When ``None``,
            this helper returns a zero-dispatch summary without
            attempting any sends.
        recipients: Resolved ``(user_id, email)`` tuples.
        cycle: The Open cycle (provides context for template rendering).

    Returns:
        DispatchSummary: Aggregate counters.
    """
    total = len(recipients)
    if notification_service is None or total == 0:
        return DispatchSummary(total_recipients=total, sent=0, errors=0)

    context = {
        "cycle_fiscal_year": cycle.fiscal_year,
        "deadline": cycle.deadline.isoformat(),
        "cycle_url": f"/cycles/{cycle.id}",
    }
    try:
        notifications = await notification_service.send_batch(
            template=NotificationTemplate.CYCLE_OPENED,
            recipients=recipients,
            context=context,
            related=("budget_cycle", cycle.id),
        )
    except AppError as exc:
        _LOG.warning(
            "open_cycle.notification_batch_failed",
            cycle_id=str(cycle.id),
            error=exc.code,
        )
        return DispatchSummary(total_recipients=total, sent=0, errors=total)

    sent = sum(1 for n in notifications if getattr(n, "status", "") == "sent")
    errors = sum(1 for n in notifications if getattr(n, "status", "") == "failed")
    return DispatchSummary(total_recipients=total, sent=sent, errors=errors)


# ---------------------------------------------------------------------------
# FastAPI route
# ---------------------------------------------------------------------------
@router.post(
    "/{cycle_id}/open",
    response_model=OpenCycleResponse,
)
async def open_cycle_endpoint(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin)),
) -> OpenCycleResponse:
    """Open a cycle via the full 5-step pipeline (FR-003).

    Args:
        cycle_id: Target cycle id.
        db: Injected DB session.
        user: Authenticated actor (FinanceAdmin or SystemAdmin).

    Returns:
        OpenCycleResponse: Aggregate outcome.
    """
    return await open_cycle(
        session=db,
        cycle_id=cycle_id,
        user=user,
    )
