"""Budget upload write + read facade (FR-011, FR-012, FR-013).

Implements the upload pipeline from ``specs/domain_budget_uploads.md``:
assert_open (CR-005) → scope check → validate (CR-004) → persist with
``next_version`` (CR-025) → audit (CR-006) → best-effort notification
(CR-029). SQL lives in :mod:`app.domain.budget_uploads.repo`.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.errors import (
    AppError,
    BatchValidationError,
    ForbiddenError,
    InfraError,
    NotFoundError,
)
from app.core.security.models import OrgUnit, User
from app.core.security.rbac import ALL_SCOPES, scoped_org_units
from app.domain.accounts.service import AccountService
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.budget_uploads import repo as budget_repo
from app.domain.budget_uploads.models import BudgetLine, BudgetUpload, UploadStatus
from app.domain.budget_uploads.validator import BudgetUploadValidator
from app.domain.cycles.models import BudgetCycle
from app.domain.cycles.service import CycleService
from app.domain.notifications.service import NotificationService
from app.domain.notifications.templates import NotificationTemplate
from app.infra import storage as storage_module
from app.infra.crypto import encrypt_field
from app.infra.db.helpers import next_version

__all__ = ["BudgetUploadService"]


_LOG = structlog.get_logger(__name__)


class BudgetUploadService:
    """Write + read facade for :class:`BudgetUpload` and :class:`BudgetLine`.

    Constructed per-request with an :class:`AsyncSession`. Downstream
    collaborators (cycles / accounts / audit / notifications) share the
    same session so the caller-owned transaction boundary extends across
    the full pipeline. Tests override ``_cycles`` / ``_accounts`` /
    ``_audit`` / ``_notifications`` after construction.
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
                the upload pipeline silently skips the email dispatch
                (best-effort per CR-029 — never invalidates the upload).
        """
        self._db = db
        self._validator = BudgetUploadValidator()
        self._cycles: CycleService = CycleService(db)
        self._accounts: AccountService = AccountService(db)
        self._audit: AuditService = AuditService(db)
        self._notifications: NotificationService | None = notifications

    # ================================================================
    #                             upload
    # ================================================================
    async def upload(
        self,
        *,
        cycle_id: UUID,
        org_unit_id: UUID,
        filename: str,
        content: bytes,
        user: User,
    ) -> BudgetUpload:
        """Validate and persist a new budget upload version.

        Call order (CR-005, CR-004, CR-025, CR-006, CR-029 — see module
        docstring).

        Args:
            cycle_id: Target :class:`BudgetCycle` UUID.
            org_unit_id: Target :class:`OrgUnit` UUID.
            filename: Original filename supplied by the client.
            content: Raw ``.xlsx`` bytes.
            user: Authenticated uploader.

        Returns:
            BudgetUpload: Newly inserted row with ``id`` + ``version``.

        Raises:
            AppError: ``CYCLE_004`` cycle not Open;
                ``UPLOAD_001/002/003`` batch-level validation failures.
            ForbiddenError: ``RBAC_002`` on scope mismatch.
            NotFoundError: ``UPLOAD_008`` when the org unit is missing.
            BatchValidationError: ``UPLOAD_007`` with every row-level
                ``UPLOAD_004/005/006`` error; zero rows persisted.
        """
        # --- 1. CR-005: assert cycle is Open as FIRST action -----------
        await self._cycles.assert_open(cycle_id)

        # --- 2. Scope check ---------------------------------------------
        await self._assert_scope(user=user, org_unit_id=org_unit_id)

        # --- 3. Resolve org unit + cycle for downstream context --------
        org_unit = await self._db.get(OrgUnit, org_unit_id)
        if org_unit is None:
            raise NotFoundError(
                "UPLOAD_008",
                f"org_unit {org_unit_id} not found",
            )
        cycle = await self._db.get(BudgetCycle, cycle_id)
        if cycle is None:  # pragma: no cover — assert_open raises first
            raise NotFoundError(
                "UPLOAD_008",
                f"cycle {cycle_id} not found",
            )

        # --- 4. Operational codes set ----------------------------------
        operational_codes = await self._accounts.get_operational_codes_set()

        # --- 5. CR-004: full validation BEFORE persistence -------------
        result = self._validator.validate(
            content,
            expected_dept_code=org_unit.code,
            operational_codes=operational_codes,
        )
        if not result.valid:
            raise BatchValidationError("UPLOAD_007", errors=result.errors)

        # --- 6. SHA-256 + raw file persistence (outside DB txn) --------
        file_hash = hashlib.sha256(content).digest()
        storage_key = await storage_module.save(
            category="budget_uploads",
            filename=filename,
            content=content,
        )

        # --- 7. Resolve account_code id map for the validated rows ----
        codes: set[str] = {str(row["account_code"]) for row in result.rows}
        code_id_map = await budget_repo.account_code_id_map(
            self._db,
            codes=codes,
        )

        # --- 8. Persisting transaction: header + lines ----------------
        upload = await self._persist_upload_and_lines(
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
            user=user,
            content=content,
            file_hash=file_hash,
            storage_key=storage_key,
            rows=result.rows,
            code_id_map=code_id_map,
        )

        # --- 9. CR-006: audit AFTER commit -----------------------------
        await self._audit.record(
            action=AuditAction.BUDGET_UPLOAD,
            resource_type="budget_upload",
            resource_id=upload.id,
            user_id=user.id,
            details={
                "cycle_id": str(cycle_id),
                "org_unit_id": str(org_unit_id),
                "org_unit_code": org_unit.code,
                "version": upload.version,
                "row_count": len(result.rows),
                "file_size_bytes": len(content),
                "filename": filename,
            },
        )
        await self._db.commit()

        # --- 10. CR-029: best-effort notification ---------------------
        await self._send_confirmation(
            user=user,
            upload=upload,
            cycle=cycle,
            org_unit=org_unit,
            filename=filename,
        )

        return upload

    # ================================================================
    #                             reads
    # ================================================================
    async def list_versions(
        self,
        *,
        cycle_id: UUID,
        org_unit_id: UUID,
    ) -> list[BudgetUpload]:
        """Thin wrapper around :func:`repo.list_versions`.

        Args:
            cycle_id: Target cycle UUID.
            org_unit_id: Target org unit UUID.

        Returns:
            list[BudgetUpload]: Rows ordered newest-first.
        """
        return await budget_repo.list_versions(
            self._db,
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
        )

    async def get(self, upload_id: UUID) -> BudgetUpload:
        """Return a single :class:`BudgetUpload` row by id.

        Args:
            upload_id: Target UUID.

        Returns:
            BudgetUpload: Matching row.

        Raises:
            NotFoundError: ``UPLOAD_008`` when the row does not exist.
        """
        row = await self._db.get(BudgetUpload, upload_id)
        if row is None:
            raise NotFoundError("UPLOAD_008", f"upload {upload_id} not found")
        return row

    async def get_latest(
        self,
        *,
        cycle_id: UUID,
        org_unit_id: UUID,
    ) -> BudgetUpload | None:
        """Thin wrapper around :func:`repo.get_latest`.

        Args:
            cycle_id: Target cycle UUID.
            org_unit_id: Target org unit UUID.

        Returns:
            BudgetUpload | None: Latest row or ``None``.
        """
        return await budget_repo.get_latest(
            self._db,
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
        )

    async def get_latest_by_cycle(
        self,
        cycle_id: UUID,
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """Thin wrapper around :func:`repo.get_latest_by_cycle`.

        Args:
            cycle_id: Target cycle UUID.

        Returns:
            dict[tuple[UUID, UUID], Decimal]: Aggregated budget amounts.
        """
        return await budget_repo.get_latest_by_cycle(self._db, cycle_id)

    # ================================================================
    #                          internals
    # ================================================================
    async def _assert_scope(
        self,
        *,
        user: User,
        org_unit_id: UUID,
    ) -> None:
        """Raise ``RBAC_002`` when ``org_unit_id`` is outside user scope.

        Global roles receive :data:`ALL_SCOPES` and short-circuit.
        Scoped roles must include the target id in their visible set.

        Args:
            user: Acting user.
            org_unit_id: Target org unit id.

        Raises:
            ForbiddenError: ``RBAC_002`` on scope mismatch.
        """
        scope = await scoped_org_units(user, self._db)
        if scope is ALL_SCOPES:
            return
        if org_unit_id not in scope:
            raise ForbiddenError(
                "RBAC_002",
                f"org_unit {org_unit_id} outside permitted scope",
            )

    async def _persist_upload_and_lines(
        self,
        *,
        cycle_id: UUID,
        org_unit_id: UUID,
        user: User,
        content: bytes,
        file_hash: bytes,
        storage_key: str,
        rows: list[dict[str, object]],
        code_id_map: dict[str, UUID],
    ) -> BudgetUpload:
        """Allocate the next version and insert header + line rows.

        Args:
            cycle_id: Target cycle UUID.
            org_unit_id: Target org unit UUID.
            user: Uploader.
            content: Raw workbook bytes (used only for size metadata).
            file_hash: Pre-computed SHA-256 digest.
            storage_key: Opaque key returned by :func:`infra.storage.save`.
            rows: Validated row dicts from the validator.
            code_id_map: ``{account_code: id}`` resolved before the txn.

        Returns:
            BudgetUpload: The inserted upload (with ``id`` + ``version``
            populated by the flush).

        Raises:
            BatchValidationError: ``UPLOAD_007`` when a validated code
                is not present in ``code_id_map`` — indicates the
                account master was mutated mid-upload.
        """
        version = await next_version(
            self._db,
            BudgetUpload,
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
        )
        now = now_utc()
        upload = BudgetUpload(
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
            uploader_id=user.id,
            version=version,
            file_path_enc=encrypt_field(storage_key.encode("utf-8")),
            file_hash=file_hash,
            file_size_bytes=len(content),
            row_count=len(rows),
            status=UploadStatus.valid.value,
            uploaded_at=now,
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
                    "UPLOAD_007",
                    errors=[
                        {
                            "row": clean.get("row"),
                            "column": "account_code",
                            "code": "UPLOAD_004",
                            "reason": f"Unknown account code: {code}",
                        }
                    ],
                )
            self._db.add(
                BudgetLine(
                    upload_id=upload.id,
                    account_code_id=account_code_id,
                    amount=amount,
                )
            )

        await self._db.commit()
        return upload

    async def _send_confirmation(
        self,
        *,
        user: User,
        upload: BudgetUpload,
        cycle: BudgetCycle,
        org_unit: OrgUnit,
        filename: str,
    ) -> None:
        """Send the ``UPLOAD_CONFIRMED`` notification best-effort.

        CR-029 contract: this method never raises. A missing
        :class:`NotificationService` (production calls that do not wire
        one) and a failing SMTP relay both fall through to a WARN log
        entry; the committed :class:`BudgetUpload` is returned to the
        caller regardless.

        Args:
            user: The uploader (primary recipient).
            upload: Persisted upload row.
            cycle: Parent cycle (provides ``fiscal_year``).
            org_unit: Parent org unit (provides ``name``).
            filename: Client-supplied filename used in the template.
        """
        if self._notifications is None:
            _LOG.info(
                "budget_upload.notification_skipped",
                reason="no notification service wired",
                upload_id=str(upload.id),
            )
            return

        email = _extract_email(user)
        if email is None:
            _LOG.warning(
                "budget_upload.notification_skipped",
                reason="uploader has no decodable email",
                upload_id=str(upload.id),
            )
            return

        context: dict[str, object] = {
            "version": upload.version,
            "filename": filename,
            "org_unit_name": org_unit.name,
            "cycle_fiscal_year": cycle.fiscal_year,
        }
        try:
            await self._notifications.send(
                template=NotificationTemplate.UPLOAD_CONFIRMED,
                recipient_user_id=user.id,
                recipient_email=email,
                context=context,
                related=("budget_upload", upload.id),
            )
        except (InfraError, AppError) as exc:
            # Reason: NotificationService.send already swallows
            # InfraError per CR-029, but we double-wrap here so any
            # unexpected wrapper exception still cannot reach the caller.
            _LOG.warning(
                "budget_upload.notification_failed",
                upload_id=str(upload.id),
                error=exc.code,
            )


def _extract_email(user: User) -> str | None:
    """Best-effort email decode for notification dispatch.

    Mirrors the helper in :mod:`app.domain.cycles.reminders`: production
    stores ciphertext in ``email_enc`` and tests stub it with UTF-8
    bytes. Returns ``None`` when the bytes cannot be decoded cleanly so
    the caller can log and skip instead of raising.

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
