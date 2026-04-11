"""Account master CRUD + actuals import service (FR-007, FR-008).

Owns the account master CRUD path (:meth:`AccountService.list`,
:meth:`~AccountService.upsert`, :meth:`~AccountService.get_by_code`),
the category-lookup helpers consumed by downstream importers
(CR-009 / CR-020), and the collect-then-report actuals bulk-import
(:meth:`~AccountService.import_actuals`).

CR-004 is enforced by validating every row before opening the persisting
transaction; CR-005 by running the cycle-state check first (via a lazy
``importlib`` lookup while ``domain.cycles`` is not yet shipped in Batch
4); CR-006 by committing the actuals insert and then recording the
``ACTUALS_IMPORT`` audit entry in a second short transaction.
"""

from __future__ import annotations

import importlib
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.errors import BatchValidationError, NotFoundError
from app.core.security.models import User
from app.domain._shared.queries import org_unit_code_to_id_map
from app.domain._shared.row_validation import clean_cell
from app.domain.accounts.models import AccountCategory, AccountCode, ActualExpense
from app.domain.accounts.validator import ActualsRowValidator
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.infra.tabular import parse_table


class _CycleAsserter(Protocol):
    """Structural type for the Batch-4 ``CycleService.assert_open`` call."""

    async def assert_open(self, cycle_id: UUID) -> None:
        """Raise ``CYCLE_004`` when the cycle is not Open."""
        ...


__all__ = [
    "AccountCodeRead",
    "AccountCodeWrite",
    "AccountService",
    "ImportSummary",
]


_LOG = structlog.get_logger(__name__)


# ----------------------------------------------------------------------- schemas
class AccountCodeWrite(BaseModel):
    """Request body for :meth:`AccountService.upsert`.

    Pydantic enforces type / enum membership before the service is
    called; invalid categories or missing fields are rejected with a
    422 by FastAPI.
    """

    model_config = ConfigDict(use_enum_values=False)

    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=200)
    category: AccountCategory
    level: int = Field(..., ge=1)


class AccountCodeRead(BaseModel):
    """Read model for :class:`AccountCode` rows returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    category: AccountCategory
    level: int
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ImportSummary(BaseModel):
    """Response body for :meth:`AccountService.import_actuals`."""

    cycle_id: UUID
    filename: str
    rows_imported: int
    org_units_affected: list[str]


# ----------------------------------------------------------------------- service
class AccountService:
    """CRUD + bulk-import service for the account master and actuals tables.

    Constructed per-request with an active :class:`AsyncSession`. The
    :class:`AuditService` is lazily constructed from the same session
    (matching the pattern used by :class:`NotificationService`), so
    tests can override it by assigning ``service._audit`` after
    instantiation.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active async session.

        Args:
            db: Active :class:`AsyncSession` owned by the caller.
        """
        self._db = db
        self._audit: AuditService = AuditService(db)
        self._validator = ActualsRowValidator()

    # ------------------------------------------------------------- read helpers
    async def list(
        self,
        *,
        category: AccountCategory | None = None,
    ) -> list[AccountCode]:
        """Return all account codes ordered by ``code``.

        Args:
            category: Optional :class:`AccountCategory` filter. ``None``
                returns every row.

        Returns:
            list[AccountCode]: ORM rows sorted ascending by ``code``.
        """
        stmt = select(AccountCode).order_by(AccountCode.code)
        if category is not None:
            stmt = stmt.where(AccountCode.category == category)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> AccountCode:
        """Fetch a single account code by its natural key.

        Args:
            code: Account code string (e.g. ``"5101"``).

        Returns:
            AccountCode: ORM row.

        Raises:
            NotFoundError: ``ACCOUNT_001`` when the code is missing.
        """
        stmt = select(AccountCode).where(AccountCode.code == code)
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("ACCOUNT_001", f"Account code {code!r} not found")
        return row

    async def get_operational_codes_set(self) -> set[str]:
        """Return every ``operational``-category code (CR-009).

        Used by the M3 template builder and the M4 budget upload
        validator to restrict which codes are written into the generated
        workbook / accepted by the upload validator.

        Returns:
            set[str]: The set of codes where
            ``category == AccountCategory.operational``.
        """
        return await self.get_codes_by_category(AccountCategory.operational)

    async def get_codes_by_category(self, category: AccountCategory) -> set[str]:
        """Return every code for a given category (CR-020).

        Args:
            category: :class:`AccountCategory` member (enum, never a
                string literal).

        Returns:
            set[str]: Codes matching the category.
        """
        stmt = select(AccountCode.code).where(AccountCode.category == category)
        result = await self._db.execute(stmt)
        return {row[0] for row in result.all()}

    # ------------------------------------------------------------- upsert path
    async def upsert(
        self,
        *,
        data: AccountCodeWrite,
        user: User,
    ) -> AccountCode:
        """Create or update an account code keyed by ``code``.

        The method commits the account write first and then records the
        audit entry (``ACCOUNT_CREATE`` for a fresh row, ``ACCOUNT_UPDATE``
        for a replacement) in a separate commit per CR-006.

        Args:
            data: :class:`AccountCodeWrite` request body.
            user: Authenticated acting :class:`User`.

        Returns:
            AccountCode: The persisted ORM row (with server defaults
            populated).
        """
        stmt = select(AccountCode).where(AccountCode.code == data.code)
        existing = (await self._db.execute(stmt)).scalar_one_or_none()

        now = now_utc()
        action: AuditAction
        if existing is None:
            row = AccountCode(
                code=data.code,
                name=data.name,
                category=data.category,
                level=data.level,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            self._db.add(row)
            action = AuditAction.ACCOUNT_CREATE
        else:
            existing.name = data.name
            existing.category = data.category
            existing.level = data.level
            existing.updated_at = now
            row = existing
            action = AuditAction.ACCOUNT_UPDATE

        await self._db.commit()
        await self._db.refresh(row)

        # CR-006: audit AFTER commit, BEFORE return.
        await self._audit.record(
            action=action,
            resource_type="account_code",
            resource_id=row.id,
            user_id=user.id,
            details={
                "code": row.code,
                "name": row.name,
                "category": row.category.value,
                "level": row.level,
            },
        )
        await self._db.commit()
        return row

    # -------------------------------------------------------- import_actuals
    async def import_actuals(
        self,
        *,
        cycle_id: UUID,
        filename: str,
        content: bytes,
        user: User,
        cycle_service: _CycleAsserter | None = None,
    ) -> ImportSummary:
        """Bulk-import actual expenses for a cycle (FR-008).

        Executes in order: assert cycle Open (CR-005) → parse via
        :func:`parse_table` (CR-024) → header normalization → full
        validation (CR-004) → single transaction delete-then-insert →
        commit → audit ``ACTUALS_IMPORT`` in a second commit (CR-006).

        Args:
            cycle_id: Target cycle UUID.
            filename: Upload filename (used for extension dispatch).
            content: Raw file bytes.
            user: Authenticated acting user.
            cycle_service: Optional injected cycle service; when
                ``None`` the method tries a lazy ``importlib`` lookup
                and skips the check (with a warning) if Batch 4 has
                not yet shipped.

        Returns:
            ImportSummary: Row count and affected org unit codes.

        Raises:
            BatchValidationError: ``ACCOUNT_002`` on any row error.
        """
        # --- 1. CR-005: cycle state assertion FIRST ---------------------
        await self._assert_cycle_open(cycle_id, cycle_service)

        # --- 2. CR-024: infra dispatch ----------------------------------
        raw_rows = await parse_table(filename, content)

        # --- 3. header normalization + required column check -----------
        normalized_rows, header_errors = self._normalize_headers(raw_rows)
        if header_errors:
            raise BatchValidationError("ACCOUNT_002", errors=header_errors)

        # --- 4. CR-004: full validation BEFORE persisting --------------
        org_unit_map = await org_unit_code_to_id_map(self._db)
        # Reason: FR-008 actuals accept every account code regardless of
        # category; unknown codes surface uniformly as ACCOUNT_002 row
        # errors through the validator.
        account_codes = await self._load_all_codes_set()
        result = self._validator.validate(
            normalized_rows,
            org_unit_codes=org_unit_map,
            account_codes=account_codes,
        )

        if not result.valid:
            raise BatchValidationError("ACCOUNT_002", errors=result.errors)

        # --- 5. CR-004: single transaction for delete + insert ---------
        code_id_map = await self._account_code_id_map(account_codes)
        await self._db.execute(delete(ActualExpense).where(ActualExpense.cycle_id == cycle_id))
        now = now_utc()
        affected_codes: set[str] = set()
        inserted = 0
        for clean in result.rows:
            org_code: str = clean["org_unit_code"]
            account_code: str = clean["account_code"]
            amount: Decimal = clean["amount"]
            org_unit_id: UUID = clean["org_unit_id"]
            account_code_id = code_id_map.get(account_code)
            if account_code_id is None:  # pragma: no cover — defensive
                raise BatchValidationError(
                    "ACCOUNT_002",
                    errors=[
                        {
                            "row": clean.get("row"),
                            "column": "account_code",
                            "code": "ACCOUNT_002",
                            "reason": f"Unknown account code: {account_code}",
                        }
                    ],
                )
            row = ActualExpense(
                cycle_id=cycle_id,
                org_unit_id=org_unit_id,
                account_code_id=account_code_id,
                amount=amount,
                imported_at=now,
                imported_by=user.id,
                created_at=now,
                updated_at=now,
            )
            self._db.add(row)
            affected_codes.add(org_code)
            inserted += 1

        await self._db.commit()

        # --- 6. CR-006: audit AFTER commit -----------------------------
        affected_sorted = sorted(affected_codes)
        await self._audit.record(
            action=AuditAction.ACTUALS_IMPORT,
            resource_type="cycle",
            resource_id=cycle_id,
            user_id=user.id,
            details={
                "filename": filename,
                "rows_imported": inserted,
                "org_units_affected": affected_sorted,
            },
        )
        await self._db.commit()

        return ImportSummary(
            cycle_id=cycle_id,
            filename=filename,
            rows_imported=inserted,
            org_units_affected=affected_sorted,
        )

    # ------------------------------------------------------------- internals
    async def _assert_cycle_open(
        self,
        cycle_id: UUID,
        cycle_service: _CycleAsserter | None,
    ) -> None:
        """Run the CR-005 cycle state check with a deferred import fallback.

        Batch 4 wires ``CycleService.assert_open`` via real DI; in
        Batch 3 the module may not exist yet and we skip with a
        warning.

        Args:
            cycle_id: Target cycle UUID.
            cycle_service: Optional service passed by the caller.
        """
        if cycle_service is not None:
            await cycle_service.assert_open(cycle_id)
            return

        try:
            module = importlib.import_module("app.domain.cycles.service")
        except ImportError:
            _LOG.info(
                "accounts.import_actuals.cycle_check_skipped",
                reason="domain.cycles not shipped yet (Batch 4)",
                cycle_id=str(cycle_id),
            )
            return

        service_cls = getattr(module, "CycleService", None)
        if service_cls is None:  # pragma: no cover — defensive
            _LOG.info(
                "accounts.import_actuals.cycle_check_skipped",
                reason="CycleService class not found",
                cycle_id=str(cycle_id),
            )
            return
        service = service_cls(self._db)
        await service.assert_open(cycle_id)

    def _normalize_headers(
        self,
        raw_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Normalize header casing and reject missing required columns.

        Args:
            raw_rows: Raw rows from :func:`parse_table`.

        Returns:
            tuple: ``(normalized_rows, header_errors)`` — errors empty on
            success.
        """
        if not raw_rows:
            return [], [
                {
                    "row": 0,
                    "column": None,
                    "code": "ACCOUNT_002",
                    "reason": "Uploaded file contains no rows",
                }
            ]

        # Normalize every row's keys. Source files may have any casing.
        normalized: list[dict[str, Any]] = []
        seen_headers: set[str] = set()
        for raw in raw_rows:
            row: dict[str, Any] = {}
            for key, value in raw.items():
                cleaned_key = clean_cell(key)
                if cleaned_key is None:
                    continue
                lower = cleaned_key.lower()
                row[lower] = value
                seen_headers.add(lower)
            normalized.append(row)

        required = {"org_unit_code", "account_code", "amount"}
        # Reason: some downstream files use ``dept_id`` as the spec alias.
        if "org_unit_code" not in seen_headers and "dept_id" in seen_headers:
            for row in normalized:
                if "org_unit_code" not in row and "dept_id" in row:
                    row["org_unit_code"] = row["dept_id"]
            seen_headers.add("org_unit_code")

        missing = required - seen_headers
        if missing:
            return normalized, [
                {
                    "row": 0,
                    "column": None,
                    "code": "ACCOUNT_002",
                    "reason": f"Missing required column(s): {sorted(missing)}",
                }
            ]
        return normalized, []

    async def _load_all_codes_set(self) -> set[str]:
        """Return every account code regardless of category."""
        stmt = select(AccountCode.code)
        result = await self._db.execute(stmt)
        return {row[0] for row in result.all()}

    async def _account_code_id_map(self, codes: set[str]) -> dict[str, UUID]:
        """Return a ``{code: id}`` map for the requested account codes.

        Args:
            codes: Set of account-code strings to resolve.

        Returns:
            dict[str, UUID]: Mapping of code → id; missing codes omitted.
        """
        if not codes:
            return {}
        stmt = select(AccountCode.code, AccountCode.id).where(AccountCode.code.in_(codes))
        result = await self._db.execute(stmt)
        mapping: dict[str, UUID] = {}
        for row in result.all():
            code, code_id = row
            mapping[code] = code_id
        return mapping
