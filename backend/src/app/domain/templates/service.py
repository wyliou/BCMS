"""Template generation + download service (FR-009, FR-010).

Owns:

* Per-filing-unit generation loop with per-unit failure isolation
  (FR-009 + CR-034 zero-actuals).
* Regeneration of a single unit's template (called by the admin UI).
* Scope-checked download path (FR-010 + CR-011).

SQL is delegated to :mod:`app.domain.templates.repo`; every write path
follows CR-006 — commit the domain state first, then record the audit
row in a second transaction.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.core.security.models import User
from app.core.security.rbac import ALL_SCOPES, scoped_org_units
from app.domain.accounts.models import AccountCategory, AccountCode
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.cycles.models import BudgetCycle, OrgUnit
from app.domain.templates.builder import build_template_workbook
from app.domain.templates.models import TemplateStatus
from app.domain.templates.repo import (
    fetch_actuals,
    fetch_template,
    upsert_error_row,
    upsert_generated_row,
)
from app.infra.crypto import decrypt_field
from app.infra.storage import read as storage_read
from app.infra.storage import save as storage_save

__all__ = ["TemplateGenerationResult", "TemplateService"]


_LOG = structlog.get_logger(__name__)


class TemplateGenerationResult(BaseModel):
    """Per-unit outcome of a template generation or regeneration call.

    Attributes:
        org_unit_id: Filing unit id.
        status: ``"generated"`` on success, ``"error"`` on per-unit
            failure (per-unit failures do not abort the batch).
        error: Human-readable error message when ``status == "error"``;
            ``None`` on success.
        template_id: Inserted / updated :class:`ExcelTemplate` row id,
            or ``None`` when error-row persistence also failed.
    """

    model_config = ConfigDict(from_attributes=True)

    org_unit_id: UUID
    status: Literal["generated", "error"]
    error: str | None = None
    template_id: UUID | None = None


class TemplateService:
    """Write + read facade for :class:`ExcelTemplate`.

    Constructed per-request with an active :class:`AsyncSession`. The
    :class:`AuditService` is lazily constructed on the same session so
    tests can override it by assigning ``service._audit`` after
    instantiation (matching the pattern used by
    :class:`app.domain.accounts.service.AccountService`).
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active async session.

        Args:
            db: Active :class:`AsyncSession` owned by the caller.
        """
        self._db = db
        self._audit: AuditService = AuditService(db)

    # ------------------------------------------------------------- reads
    async def _load_operational_accounts(self) -> list[AccountCode]:
        """Return every operational-category :class:`AccountCode` row.

        Uses :class:`AccountCategory.operational` directly (CR-020) and
        orders the rows by ``code`` so every template has a stable,
        reviewable layout.

        Returns:
            list[AccountCode]: Operational-category rows, sorted by code.
        """
        stmt = (
            select(AccountCode)
            .where(AccountCode.category == AccountCategory.operational)
            .order_by(AccountCode.code)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # --------------------------------------------------------- generation
    async def generate_for_cycle(
        self,
        *,
        cycle: BudgetCycle,
        filing_units: list[OrgUnit],
        user: User,
    ) -> list[TemplateGenerationResult]:
        """Generate a template workbook for every provided filing unit.

        Per-unit failures are captured as
        :class:`TemplateGenerationResult` rows with ``status='error'``
        and the exception message; the loop keeps going so one bad unit
        never aborts the full batch (FR-009).

        Args:
            cycle: The Open :class:`BudgetCycle` — the caller (Batch 6
                open-cycle orchestrator) guarantees the cycle is Open.
            filing_units: :class:`OrgUnit` rows to generate for. Already
                excludes ``0000公司`` and any unit whose
                ``excluded_for_cycle_ids`` contains ``cycle.id``.
            user: Acting user (threaded into audit rows and the
                ``generated_by`` column).

        Returns:
            list[TemplateGenerationResult]: One entry per filing unit in
            input order.
        """
        # Reason: a failure to fetch operational codes is fatal (pre-loop)
        # — propagate rather than suppress, per the spec "per-unit isolation
        # only" rule.
        operational_accounts = await self._load_operational_accounts()

        results: list[TemplateGenerationResult] = []
        for unit in filing_units:
            result = await self._generate_single_unit(
                cycle=cycle,
                org_unit=unit,
                operational_accounts=operational_accounts,
                user=user,
            )
            results.append(result)
        return results

    async def regenerate(
        self,
        *,
        cycle: BudgetCycle,
        org_unit: OrgUnit,
        user: User,
    ) -> TemplateGenerationResult:
        """Regenerate the template for a single filing unit.

        Reuses :meth:`_generate_single_unit` so success and error
        semantics match :meth:`generate_for_cycle` exactly.

        Args:
            cycle: Target cycle (caller provides; not re-fetched).
            org_unit: Target filing unit.
            user: Acting user (must carry FinanceAdmin or SystemAdmin
                at the route layer).

        Returns:
            TemplateGenerationResult: Outcome for the single unit.
        """
        operational_accounts = await self._load_operational_accounts()
        return await self._generate_single_unit(
            cycle=cycle,
            org_unit=org_unit,
            operational_accounts=operational_accounts,
            user=user,
        )

    async def _generate_single_unit(
        self,
        *,
        cycle: BudgetCycle,
        org_unit: OrgUnit,
        operational_accounts: list[AccountCode],
        user: User,
    ) -> TemplateGenerationResult:
        """Generate one unit's template, catching any failure locally.

        Args:
            cycle: Target Open cycle.
            org_unit: Target filing unit.
            operational_accounts: Pre-fetched operational-category rows.
            user: Acting user.

        Returns:
            TemplateGenerationResult: Success or captured-error entry.
        """
        try:
            actuals = await fetch_actuals(
                self._db,
                cycle_id=cycle.id,
                org_unit_id=org_unit.id,
            )
            content = await build_template_workbook(
                cycle=cycle,
                org_unit=org_unit,
                operational_accounts=operational_accounts,
                actuals=actuals,
            )
            filename = _template_filename(org_unit=org_unit, cycle=cycle)
            storage_key = await storage_save(
                category="templates",
                filename=filename,
                content=content,
            )
            template = await upsert_generated_row(
                self._db,
                cycle_id=cycle.id,
                org_unit_id=org_unit.id,
                storage_key=storage_key,
                content=content,
                user=user,
            )
            await self._db.commit()

            # CR-006: audit AFTER commit, BEFORE return.
            await self._audit.record(
                action=AuditAction.TEMPLATE_GENERATE,
                resource_type="excel_template",
                resource_id=template.id,
                user_id=user.id,
                details={
                    "cycle_id": str(cycle.id),
                    "org_unit_id": str(org_unit.id),
                    "org_unit_code": org_unit.code,
                    "filename": filename,
                },
            )
            await self._db.commit()

            return TemplateGenerationResult(
                org_unit_id=org_unit.id,
                status="generated",
                error=None,
                template_id=template.id,
            )
        except Exception as exc:
            # Reason: FR-009 mandates per-unit failure isolation — catch
            # every exception so one bad unit never aborts the full batch.
            await self._db.rollback()
            _LOG.error(
                "template.generation_failed",
                cycle_id=str(cycle.id),
                org_unit_id=str(org_unit.id),
                error=str(exc),
            )
            return await self._persist_error_result(
                cycle=cycle,
                org_unit=org_unit,
                user=user,
                error_message=str(exc),
            )

    async def _persist_error_result(
        self,
        *,
        cycle: BudgetCycle,
        org_unit: OrgUnit,
        user: User,
        error_message: str,
    ) -> TemplateGenerationResult:
        """Persist a generation-error row in a best-effort transaction.

        Args:
            cycle: Target cycle.
            org_unit: Target filing unit.
            user: Acting user.
            error_message: Exception message captured at the generation
                failure site.

        Returns:
            TemplateGenerationResult: Status=``error`` result. The
            ``template_id`` field is ``None`` when the error-row persist
            also failed — the orchestrator still receives a typed entry
            for every unit in that case.
        """
        try:
            template = await upsert_error_row(
                self._db,
                cycle_id=cycle.id,
                org_unit_id=org_unit.id,
                user=user,
                error_message=error_message,
            )
            await self._db.commit()
            template_id: UUID | None = template.id
        except Exception as inner:
            # Reason: error-row persistence is best-effort — never
            # propagate a secondary failure up to the caller.
            await self._db.rollback()
            _LOG.error(
                "template.error_row_persist_failed",
                cycle_id=str(cycle.id),
                org_unit_id=str(org_unit.id),
                error=str(inner),
            )
            template_id = None

        return TemplateGenerationResult(
            org_unit_id=org_unit.id,
            status="error",
            error=error_message,
            template_id=template_id,
        )

    # ----------------------------------------------------------- download
    async def download(
        self,
        *,
        cycle_id: UUID,
        org_unit_id: UUID,
        user: User,
    ) -> tuple[str, bytes]:
        """Return the generated template bytes for a filing unit.

        Enforces the CR-011 scope check (a FilingUnitManager or
        UplineReviewer can only download their own unit's template),
        verifies the row exists and is not in the error state, reads
        the bytes from storage, increments ``download_count`` and
        records an audit entry per CR-006.

        Args:
            cycle_id: Target cycle id.
            org_unit_id: Target filing unit id.
            user: Acting user.

        Returns:
            tuple[str, bytes]: ``(filename, workbook_bytes)`` pair.

        Raises:
            ForbiddenError: ``RBAC_002`` when ``org_unit_id`` is outside
                the user's scope.
            NotFoundError: ``TPL_002`` when the template row is
                missing or carries a generation error.
        """
        # 1. CR-011 — scope check BEFORE any DB lookup.
        scope = await scoped_org_units(user, self._db)
        if scope is not ALL_SCOPES and org_unit_id not in scope:
            raise ForbiddenError(
                "RBAC_002",
                f"org_unit {org_unit_id} is outside your permitted scope",
            )

        # 2. Fetch + existence / status check.
        template = await fetch_template(
            self._db,
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
        )
        if template is None or template.status != TemplateStatus.generated:
            raise NotFoundError(
                "TPL_002",
                f"Template not generated for cycle={cycle_id} org_unit={org_unit_id}",
            )

        # 3. Read bytes via infra.storage.
        storage_key = decrypt_field(template.file_path_enc).decode("utf-8")
        content = await storage_read(storage_key)

        # 4. Increment download_count + commit.
        template.download_count += 1
        await self._db.commit()

        # 5. CR-006: audit AFTER commit.
        await self._audit.record(
            action=AuditAction.TEMPLATE_DOWNLOAD,
            resource_type="excel_template",
            resource_id=template.id,
            user_id=user.id,
            details={
                "cycle_id": str(cycle_id),
                "org_unit_id": str(org_unit_id),
                "download_count": template.download_count,
            },
        )
        await self._db.commit()

        # 6. Build filename from the org-unit code (needs a round-trip).
        org_unit = await self._db.get(OrgUnit, org_unit_id)
        cycle = await self._db.get(BudgetCycle, cycle_id)
        if org_unit is None or cycle is None:  # pragma: no cover — defensive
            raise NotFoundError(
                "TPL_002",
                f"Template parent rows missing for {cycle_id}/{org_unit_id}",
            )
        filename = _template_filename(org_unit=org_unit, cycle=cycle)
        return filename, content


def _template_filename(*, org_unit: OrgUnit, cycle: BudgetCycle) -> str:
    """Build the canonical download filename for a template.

    Args:
        org_unit: The filing unit (provides ``code``).
        cycle: The cycle (provides ``fiscal_year``).

    Returns:
        str: Filename of the form ``{code}_{fiscal_year}_budget_template.xlsx``.
    """
    return f"{org_unit.code}_{cycle.fiscal_year}_budget_template.xlsx"
