"""Personnel budget import service (FR-024, FR-025, FR-026).

Implements the import pipeline from ``specs/domain_personnel.md``:
assert_open (CR-005) → size check (CR-030) → parse (CR-024) → header
normalization (CR-019) → row count check (CR-030) → validate (CR-004)
→ persist with next_version (CR-025) → audit (CR-006) → best-effort
batch notification to FinanceAdmin (CR-029).
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import BatchValidationError, InfraError, NotFoundError
from app.core.security.models import User
from app.core.security.roles import Role
from app.domain._shared.queries import org_unit_code_to_id_map
from app.domain.accounts.models import AccountCategory, AccountCode
from app.domain.accounts.service import AccountService
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.cycles.service import CycleService
from app.domain.notifications.service import NotificationService
from app.domain.notifications.templates import NotificationTemplate
from app.domain.personnel.models import PersonnelBudgetLine, PersonnelBudgetUpload
from app.domain.personnel.validator import PersonnelImportValidator
from app.infra import storage as storage_module
from app.infra.db.helpers import next_version
from app.infra.tabular import parse_table

__all__ = ["PersonnelImportService"]


_LOG = structlog.get_logger(__name__)


class PersonnelImportService:
    """Write + read facade for personnel budget imports.

    Constructed per-request with an :class:`AsyncSession`. Downstream
    collaborators (cycles / accounts / audit / notifications) share the
    same session so the caller-owned transaction boundary extends across
    the full pipeline. Tests override collaborators after construction.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        notifications: NotificationService | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            db: Active :class:`AsyncSession`.
            notifications: Optional pre-wired :class:`NotificationService`.
                Tests inject a fake; production leaves this ``None`` and
                the import pipeline skips email dispatch (best-effort per
                CR-029 — never invalidates the import).
        """
        self._db = db
        self._validator = PersonnelImportValidator()
        self._cycles: CycleService = CycleService(db)
        self._accounts: AccountService = AccountService(db)
        self._audit: AuditService = AuditService(db)
        self._notifications: NotificationService | None = notifications

    # ================================================================
    #                             import_
    # ================================================================
    async def import_(
        self,
        *,
        cycle_id: UUID,
        filename: str,
        content: bytes,
        user: User,
    ) -> PersonnelBudgetUpload:
        """Validate and persist a new personnel budget import version.

        Asserts cycle is Open, validates all rows (collect-then-report),
        persists header + lines transactionally, notifies FinanceAdmin
        on success.

        Call order enforces CR-005, CR-030, CR-024, CR-019, CR-004,
        CR-025, CR-006, CR-029.

        Args:
            cycle_id: UUID of the target cycle.
            filename: Original filename (.csv or .xlsx).
            content: Raw file bytes.
            user: Authenticated HRAdmin performing the import.

        Returns:
            PersonnelBudgetUpload: Newly created ORM row with version,
            snapshot, and affected_org_units_summary.

        Raises:
            AppError: ``CYCLE_004`` when the cycle is not Open.
            BatchValidationError: ``PERS_004`` when any row fails or
                file size / row count limits are exceeded; zero rows
                persisted (CR-004).
        """
        settings = get_settings()

        # --- 1. CR-005: assert cycle is Open — FIRST action ------------
        await self._cycles.assert_open(cycle_id)

        # --- 2. CR-030: file size check (batch-level) ------------------
        if len(content) > settings.max_upload_bytes:
            raise BatchValidationError(
                "PERS_004",
                errors=[
                    {
                        "row": 0,
                        "column": None,
                        "code": "PERS_004",
                        "reason": "file_too_large",
                    }
                ],
            )

        # --- 3. CR-024: parse file via infra.tabular dispatcher --------
        raw_rows = await parse_table(filename, content)

        # --- 4. CR-030: row count check (batch-level) ------------------
        if len(raw_rows) > settings.max_upload_rows:
            raise BatchValidationError(
                "PERS_004",
                errors=[
                    {
                        "row": 0,
                        "column": None,
                        "code": "PERS_004",
                        "reason": "too_many_rows",
                    }
                ],
            )

        # --- 5. CR-018: resolve org_unit_codes map ---------------------
        org_unit_codes = await org_unit_code_to_id_map(self._db)

        # --- 6. CR-020: fetch personnel category codes -----------------
        personnel_codes = await self._accounts.get_codes_by_category(AccountCategory.personnel)

        # --- 7. CR-004: full validation BEFORE persistence -------------
        result = self._validator.validate(
            raw_rows,
            org_unit_codes=org_unit_codes,
            personnel_codes=personnel_codes,
        )
        if not result.valid:
            raise BatchValidationError("PERS_004", errors=result.errors)

        # --- 8. Resolve account_code_id map for validated rows ---------
        codes: set[str] = {str(row["account_code"]) for row in result.rows}
        code_id_map = await _account_code_id_map(self._db, codes=codes)

        # --- 9. Compute affected_org_units_summary ---------------------
        affected_summary = _build_affected_summary(result.rows)

        # --- 10. Save raw content to storage ---------------------------
        # Reason: storage_key is intentionally discarded; the service
        # stores file_hash instead to avoid exposing filesystem paths.
        await storage_module.save(
            category="personnel",
            filename=filename,
            content=content,
        )
        file_hash = hashlib.sha256(content).hexdigest()

        # --- 11. Persist: next_version + header + lines (CR-025) ------
        upload = await self._persist_upload_and_lines(
            cycle_id=cycle_id,
            user=user,
            filename=filename,
            file_hash=file_hash,
            rows=result.rows,
            code_id_map=code_id_map,
            affected_summary=affected_summary,
        )

        # --- 12. CR-006: audit AFTER commit ----------------------------
        await self._audit.record(
            action=AuditAction.PERSONNEL_IMPORT,
            resource_type="personnel_budget_upload",
            resource_id=upload.id,
            user_id=user.id,
            details={
                "cycle_id": str(cycle_id),
                "version": upload.version,
                "row_count": len(result.rows),
                "file_size_bytes": len(content),
                "filename": filename,
            },
        )
        await self._db.commit()

        # --- 13. CR-029: best-effort batch notification to FinanceAdmin
        await self._send_batch_notification(upload=upload, filename=filename)

        return upload

    # ================================================================
    #                             reads
    # ================================================================
    async def list_versions(
        self,
        cycle_id: UUID,
    ) -> list[PersonnelBudgetUpload]:
        """Return all personnel import versions for a cycle.

        Args:
            cycle_id: UUID of the cycle.

        Returns:
            list[PersonnelBudgetUpload]: All versions ordered by version
            ascending (read-only history).
        """
        stmt = (
            select(PersonnelBudgetUpload)
            .where(PersonnelBudgetUpload.cycle_id == cycle_id)
            .order_by(PersonnelBudgetUpload.version.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, upload_id: UUID) -> PersonnelBudgetUpload:
        """Fetch a single personnel import by UUID.

        Args:
            upload_id: UUID of the personnel import.

        Returns:
            PersonnelBudgetUpload: ORM row.

        Raises:
            NotFoundError: ``PERS_004`` when the row does not exist.
        """
        row = await self._db.get(PersonnelBudgetUpload, upload_id)
        if row is None:
            raise NotFoundError("PERS_004", f"personnel import {upload_id} not found")
        return row

    async def get_latest_by_cycle(
        self,
        cycle_id: UUID,
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """Return a map of (org_unit_id, account_code_id) -> amount from latest version.

        Used by ConsolidatedReportService (M7) to join personnel amounts.
        Aggregates lines from the highest-version upload for the cycle.

        Args:
            cycle_id: UUID of the cycle.

        Returns:
            dict[tuple[UUID, UUID], Decimal]: Personnel amounts from highest
            version. Empty dict when no imports exist for the cycle.
        """
        # Fetch the latest upload for the cycle.
        latest_stmt = (
            select(PersonnelBudgetUpload)
            .where(PersonnelBudgetUpload.cycle_id == cycle_id)
            .order_by(PersonnelBudgetUpload.version.desc())
            .limit(1)
        )
        latest_result = await self._db.execute(latest_stmt)
        latest_upload = latest_result.scalars().first()
        if latest_upload is None:
            return {}

        # Fetch all lines for that upload.
        lines_stmt = select(PersonnelBudgetLine).where(
            PersonnelBudgetLine.upload_id == latest_upload.id
        )
        lines_result = await self._db.execute(lines_stmt)
        lines = list(lines_result.scalars().all())

        aggregated: dict[tuple[UUID, UUID], Decimal] = {}
        for line in lines:
            key = (line.org_unit_id, line.account_code_id)
            aggregated[key] = aggregated.get(key, Decimal("0")) + line.amount
        return aggregated

    # ================================================================
    #                          internals
    # ================================================================
    async def _persist_upload_and_lines(
        self,
        *,
        cycle_id: UUID,
        user: User,
        filename: str,
        file_hash: str,
        rows: list[dict[str, Any]],
        code_id_map: dict[str, UUID],
        affected_summary: list[dict[str, str]],
    ) -> PersonnelBudgetUpload:
        """Allocate the next version and insert header + line rows.

        Args:
            cycle_id: Target cycle UUID.
            user: Importer user.
            filename: Original filename.
            file_hash: SHA-256 hex digest of the uploaded bytes.
            rows: Validated row dicts from the validator.
            code_id_map: ``{account_code: id}`` resolved before the txn.
            affected_summary: Pre-computed affected_org_units_summary list.

        Returns:
            PersonnelBudgetUpload: The inserted upload row with version
            and id populated by the flush.

        Raises:
            BatchValidationError: ``PERS_004`` when a validated code is
                not present in ``code_id_map`` — indicates the account
                master was mutated mid-import.
        """
        # CR-025: next_version inside the same transaction.
        version = await next_version(
            self._db,
            PersonnelBudgetUpload,
            cycle_id=cycle_id,
        )
        now = now_utc()
        upload = PersonnelBudgetUpload(
            cycle_id=cycle_id,
            uploader_user_id=user.id,
            uploaded_at=now,
            filename=filename,
            file_hash=file_hash,
            version=version,
            affected_org_units_summary={
                "unit_count": len({row["org_unit_id"] for row in rows}),
                "unit_codes": affected_summary,
            },
        )
        self._db.add(upload)
        await self._db.flush()

        for clean in rows:
            code = str(clean["account_code"])
            amount = clean["amount"]
            if not isinstance(amount, Decimal):  # pragma: no cover — defensive
                amount = Decimal(str(amount))
            account_code_id = code_id_map.get(code)
            if account_code_id is None:
                await self._db.rollback()
                raise BatchValidationError(
                    "PERS_004",
                    errors=[
                        {
                            "row": 0,
                            "column": "account_code",
                            "code": "PERS_002",
                            "reason": f"Unknown account code: {code}",
                        }
                    ],
                )
            self._db.add(
                PersonnelBudgetLine(
                    upload_id=upload.id,
                    org_unit_id=clean["org_unit_id"],
                    account_code_id=account_code_id,
                    amount=amount,
                )
            )

        await self._db.commit()
        return upload

    async def _send_batch_notification(
        self,
        *,
        upload: PersonnelBudgetUpload,
        filename: str,
    ) -> None:
        """Send PERSONNEL_IMPORTED notification to FinanceAdmin users best-effort.

        CR-029 contract: this method never raises. A missing
        :class:`NotificationService` (production calls without one wired)
        and a failing SMTP relay both fall through to a WARN log entry;
        the committed :class:`PersonnelBudgetUpload` is returned to the
        caller regardless.

        Args:
            upload: Persisted upload row.
            filename: Client-supplied filename used in the template.
        """
        if self._notifications is None:
            _LOG.info(
                "personnel_import.notification_skipped",
                reason="no notification service wired",
                upload_id=str(upload.id),
            )
            return

        # Resolve FinanceAdmin recipients from Users table.
        recipients = await _get_finance_admin_recipients(self._db)
        if not recipients:
            _LOG.warning(
                "personnel_import.notification_skipped",
                reason="no FinanceAdmin recipients found",
                upload_id=str(upload.id),
            )
            return

        context: dict[str, Any] = {
            "version": upload.version,
            "filename": filename,
        }
        try:
            await self._notifications.send_batch(
                template=NotificationTemplate.PERSONNEL_IMPORTED,
                recipients=recipients,
                context=context,
                related=("personnel_budget_upload", upload.id),
            )
        except (InfraError, Exception) as exc:
            # Reason: CR-029 — notification failure must not propagate.
            _LOG.warning(
                "personnel_import.notification_failed",
                upload_id=str(upload.id),
                error=str(exc),
            )


def _build_affected_summary(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Compute the affected_org_units_summary from validated rows.

    Groups rows by org_unit_id and sums amounts per unit.

    Args:
        rows: Validated rows with ``org_unit_id``, ``account_code``,
            and ``amount``.

    Returns:
        list[dict[str, str]]: One entry per distinct org_unit_id
        containing ``org_unit_id`` and ``total_amount`` as strings.
    """
    totals: dict[UUID, Decimal] = {}
    for row in rows:
        uid: UUID = row["org_unit_id"]
        amount: Decimal = row["amount"]
        totals[uid] = totals.get(uid, Decimal("0")) + amount

    return [{"org_unit_id": str(uid), "total_amount": str(total)} for uid, total in totals.items()]


async def _account_code_id_map(
    db: AsyncSession,
    *,
    codes: set[str],
) -> dict[str, UUID]:
    """Return a ``{code: id}`` map for the requested account codes.

    Args:
        db: Active async session.
        codes: Set of account-code strings to resolve.

    Returns:
        dict[str, UUID]: Mapping from code string to UUID.
        Unknown codes are simply absent.
    """
    if not codes:
        return {}
    stmt = select(AccountCode.code, AccountCode.id).where(AccountCode.code.in_(codes))
    result = await db.execute(stmt)
    mapping: dict[str, UUID] = {}
    for row in result.all():
        code, code_id = row
        mapping[code] = code_id
    return mapping


async def _get_finance_admin_recipients(
    db: AsyncSession,
) -> list[tuple[UUID, str]]:
    """Query User rows with FinanceAdmin role and extract email addresses.

    Args:
        db: Active async session.

    Returns:
        list[tuple[UUID, str]]: List of ``(user_id, email)`` tuples
        for every active FinanceAdmin. Email is decoded from ``email_enc``
        bytes as UTF-8; non-decodable rows are skipped with a WARN.
    """
    from app.core.security.models import User as UserModel

    stmt = select(UserModel).where(UserModel.is_active.is_(True))
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    recipients: list[tuple[UUID, str]] = []
    for user in users:
        if Role.FinanceAdmin.value not in (user.roles or []):
            continue
        raw = user.email_enc or b""
        if not raw:
            continue
        try:
            email = raw.decode("utf-8")
        except UnicodeDecodeError:
            _LOG.warning("personnel_import.bad_email_enc", user_id=str(user.id))
            continue
        if "@" not in email:
            continue
        recipients.append((user.id, email))
    return recipients
