"""Shared cost import write + read facade (FR-027, FR-028, FR-029).

Implements the upload pipeline from ``specs/domain_shared_costs.md``:
assert_open (CR-005) → size/row-count checks (CR-030) → parse_table (CR-024)
→ header normalization (CR-019) → validate (CR-004) → diff prev version
→ persist with next_version (CR-025) → commit → audit (CR-006)
→ best-effort per-unit notifications (CR-029).
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import AppError, BatchValidationError, InfraError, NotFoundError
from app.core.security.models import OrgUnit, User
from app.domain._shared.queries import org_unit_code_to_id_map
from app.domain.accounts.models import AccountCategory, AccountCode
from app.domain.accounts.service import AccountService
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.cycles.service import CycleService
from app.domain.notifications.service import NotificationService
from app.domain.notifications.templates import NotificationTemplate
from app.domain.shared_costs.models import SharedCostLine, SharedCostUpload
from app.domain.shared_costs.validator import SharedCostImportValidator, normalize_headers
from app.infra import storage as storage_module
from app.infra.db.helpers import next_version
from app.infra.tabular import parse_table

__all__ = ["SharedCostImportService"]

_LOG = structlog.get_logger(__name__)


def diff_affected_units(
    prev_lines: list[SharedCostLine],
    new_lines: list[SharedCostLine],
) -> set[UUID]:
    """Compute org unit IDs affected by a shared cost version change.

    An org unit is affected if: its aggregate amount changed, it is new in
    the new version, or it was present in the previous but absent in the new.
    Symmetric diff semantics: any non-zero change counts.

    Args:
        prev_lines: SharedCostLine rows from the previous version (may be empty).
        new_lines: SharedCostLine rows from the new version.

    Returns:
        set[UUID]: Unique org_unit_ids that are affected.
    """
    # Reason: aggregate total amount per org_unit_id for each version,
    # then compare the two dicts. Any unit present in only one, or with
    # differing totals, is "affected".
    prev_totals: dict[UUID, Decimal] = {}
    for line in prev_lines:
        prev_totals[line.org_unit_id] = (
            prev_totals.get(line.org_unit_id, Decimal("0")) + line.amount
        )

    new_totals: dict[UUID, Decimal] = {}
    for line in new_lines:
        new_totals[line.org_unit_id] = new_totals.get(line.org_unit_id, Decimal("0")) + line.amount

    all_units: set[UUID] = set(prev_totals) | set(new_totals)
    affected: set[UUID] = set()
    for unit_id in all_units:
        if prev_totals.get(unit_id) != new_totals.get(unit_id):
            affected.add(unit_id)
    return affected


class SharedCostImportService:
    """Write + read facade for :class:`SharedCostUpload` and :class:`SharedCostLine`.

    Constructed per-request with an :class:`AsyncSession`. Downstream
    collaborators (cycles / accounts / audit / notifications) share the
    same session so the caller-owned transaction boundary extends across
    the full pipeline.
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
                the import pipeline silently skips email dispatch
                (best-effort per CR-029 — never invalidates the import).
        """
        self._db = db
        self._validator = SharedCostImportValidator()
        self._cycles = CycleService(db)
        self._accounts = AccountService(db)
        self._audit = AuditService(db)
        self._notifications: NotificationService | None = notifications

    # ================================================================
    #                            import_
    # ================================================================
    async def import_(
        self,
        *,
        cycle_id: UUID,
        filename: str,
        content: bytes,
        user: User,
    ) -> SharedCostUpload:
        """Validate and persist a new shared cost import version.

        Asserts cycle is Open, validates all rows (collect-then-report), persists
        header + lines transactionally, computes diff with previous version, and
        notifies affected department managers.

        Args:
            cycle_id: UUID of the target cycle.
            filename: Original filename (.csv or .xlsx).
            content: Raw file bytes.
            user: Authenticated FinanceAdmin performing the import.

        Returns:
            SharedCostUpload: Newly created ORM row with version, diff summary.

        Raises:
            AppError: ``CYCLE_004`` if cycle is not Open.
            BatchValidationError: ``SHARED_004`` on any row/batch error.
        """
        settings = get_settings()

        # --- 1. CR-005: assert cycle is Open as FIRST action -------------
        await self._cycles.assert_open(cycle_id)

        # --- 2. CR-030: file size check (batch-level) --------------------
        if len(content) > settings.max_upload_bytes:
            raise BatchValidationError(
                "SHARED_004",
                message="file_too_large",
            )

        # --- 3. CR-024: parse table (CSV/XLSX dispatch) ------------------
        raw_rows = await parse_table(filename, content)

        # --- 4. CR-019: header normalization (batch-level) ---------------
        rows = normalize_headers(raw_rows)

        # --- 5. CR-030: row count check (batch-level) --------------------
        if len(rows) > settings.max_upload_rows:
            raise BatchValidationError(
                "SHARED_004",
                message="too_many_rows",
            )

        # --- 6. CR-018: org_unit code → id map ---------------------------
        org_unit_codes = await org_unit_code_to_id_map(self._db)

        # --- 7. CR-020: shared_cost account codes ------------------------
        shared_cost_codes = await self._accounts.get_codes_by_category(AccountCategory.shared_cost)

        # --- 8. CR-004: full validation BEFORE persistence ---------------
        result = self._validator.validate(
            rows,
            org_unit_codes=org_unit_codes,
            shared_cost_codes=shared_cost_codes,
        )
        if not result.valid:
            raise BatchValidationError("SHARED_004", errors=result.errors)

        # --- 9. Resolve account_code → id map ----------------------------
        codes: set[str] = {str(row["account_code"]) for row in result.rows}
        code_id_map = await _account_code_id_map(self._db, codes=codes)

        # --- 10. Fetch previous version lines for diff -------------------
        prev_upload = await self._get_latest(cycle_id)
        prev_lines: list[SharedCostLine] = []
        if prev_upload is not None:
            prev_lines = await _fetch_lines(self._db, upload_id=prev_upload.id)

        # --- 11. Build new lines from validated rows ---------------------
        new_lines_data = _build_lines_data(result.rows, code_id_map)

        # --- 12. Compute diff BEFORE persisting transaction --------------
        # Reason: diff_affected_units is a pure function on Python objects;
        # new_lines are not yet persisted. We construct ephemeral SharedCostLine
        # objects to match the function's signature.
        ephemeral_new_lines = _ephemeral_lines(new_lines_data)
        affected_unit_ids = diff_affected_units(prev_lines, ephemeral_new_lines)

        # --- 13. Compute affected_org_units_summary ----------------------
        unit_codes = await _resolve_unit_codes(self._db, list(affected_unit_ids))
        summary: dict[str, Any] = {
            "unit_count": len(affected_unit_ids),
            "unit_codes": unit_codes,
            "diff_changed": len(affected_unit_ids),
        }

        # --- 14. Save raw file (outside DB txn) --------------------------
        file_hash = hashlib.sha256(content).digest()
        await storage_module.save(
            category="shared_costs",
            filename=filename,
            content=content,
        )

        # --- 15. Persisting transaction: header + lines (CR-025) ---------
        upload = await self._persist_upload_and_lines(
            cycle_id=cycle_id,
            user=user,
            filename=filename,
            file_hash=file_hash,
            content=content,
            lines_data=new_lines_data,
            summary=summary,
        )

        # --- 16. CR-006: audit AFTER commit, BEFORE return ---------------
        await self._audit.record(
            action=AuditAction.SHARED_COST_IMPORT,
            resource_type="shared_cost_upload",
            resource_id=upload.id,
            user_id=user.id,
            details={
                "cycle_id": str(cycle_id),
                "version": upload.version,
                "row_count": len(result.rows),
                "file_size_bytes": len(content),
                "filename": filename,
                "affected_unit_count": len(affected_unit_ids),
            },
        )

        # --- 17. CR-029: per-unit notifications (best-effort) ------------
        await self._send_diff_notifications(
            upload=upload,
            cycle_id=cycle_id,
            affected_unit_ids=affected_unit_ids,
            prev_lines=prev_lines,
            new_lines=ephemeral_new_lines,
        )

        return upload

    # ================================================================
    #                             reads
    # ================================================================
    async def list_versions(
        self,
        cycle_id: UUID,
    ) -> list[SharedCostUpload]:
        """Return all shared cost import versions for a cycle, ordered by version asc.

        Args:
            cycle_id: UUID of the cycle.

        Returns:
            list[SharedCostUpload]: All versions (read-only history).
        """
        stmt = (
            select(SharedCostUpload)
            .where(SharedCostUpload.cycle_id == cycle_id)
            .order_by(SharedCostUpload.version.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, upload_id: UUID) -> SharedCostUpload:
        """Fetch a single shared cost import by UUID.

        Args:
            upload_id: UUID of the shared cost upload.

        Returns:
            SharedCostUpload: ORM row.

        Raises:
            NotFoundError: Import does not exist.
        """
        row = await self._db.get(SharedCostUpload, upload_id)
        if row is None:
            raise NotFoundError("SHARED_004", f"shared_cost_upload {upload_id} not found")
        return row

    async def get_latest_by_cycle(
        self,
        cycle_id: UUID,
    ) -> dict[tuple[UUID, UUID], Decimal]:
        """Return a map of (org_unit_id, account_code_id) -> amount from latest version.

        Used by ConsolidatedReportService (M7) to join shared cost amounts.

        Args:
            cycle_id: UUID of the cycle.

        Returns:
            dict[tuple[UUID, UUID], Decimal]: Shared cost amounts from highest version.
        """
        upload = await self._get_latest(cycle_id)
        if upload is None:
            return {}
        lines = await _fetch_lines(self._db, upload_id=upload.id)
        result: dict[tuple[UUID, UUID], Decimal] = {}
        for line in lines:
            key = (line.org_unit_id, line.account_code_id)
            result[key] = result.get(key, Decimal("0")) + line.amount
        return result

    # ================================================================
    #                          internals
    # ================================================================
    async def _get_latest(self, cycle_id: UUID) -> SharedCostUpload | None:
        """Return the highest-version upload for a cycle, or ``None``."""
        stmt = (
            select(SharedCostUpload)
            .where(SharedCostUpload.cycle_id == cycle_id)
            .order_by(SharedCostUpload.version.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def _persist_upload_and_lines(
        self,
        *,
        cycle_id: UUID,
        user: User,
        filename: str,
        file_hash: bytes,
        content: bytes,
        lines_data: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> SharedCostUpload:
        """Allocate next version and insert header + line rows atomically.

        Args:
            cycle_id: Target cycle UUID.
            user: Uploader.
            filename: Original filename.
            file_hash: Pre-computed SHA-256 digest.
            content: Raw bytes (for size metadata).
            lines_data: Pre-resolved line dicts with ``org_unit_id``,
                ``account_code_id``, ``amount``.
            summary: Computed ``affected_org_units_summary`` dict.

        Returns:
            SharedCostUpload: Inserted upload row with ``id`` + ``version``.
        """
        version = await next_version(
            self._db,
            SharedCostUpload,
            cycle_id=cycle_id,
        )
        now = now_utc()
        upload = SharedCostUpload(
            cycle_id=cycle_id,
            uploader_user_id=user.id,
            uploaded_at=now,
            filename=filename,
            file_hash=file_hash,
            version=version,
            affected_org_units_summary=summary,
        )
        self._db.add(upload)
        await self._db.flush()

        for data in lines_data:
            self._db.add(
                SharedCostLine(
                    upload_id=upload.id,
                    org_unit_id=data["org_unit_id"],
                    account_code_id=data["account_code_id"],
                    amount=data["amount"],
                )
            )

        await self._db.commit()
        return upload

    async def _send_diff_notifications(
        self,
        *,
        upload: SharedCostUpload,
        cycle_id: UUID,
        affected_unit_ids: set[UUID],
        prev_lines: list[SharedCostLine],
        new_lines: list[SharedCostLine],
    ) -> None:
        """Send per-affected-unit notifications best-effort (CR-029).

        Args:
            upload: Persisted upload row.
            cycle_id: Parent cycle UUID.
            affected_unit_ids: Set of org unit UUIDs that changed.
            prev_lines: Previous version lines (for amount context).
            new_lines: New version lines.
        """
        if self._notifications is None:
            _LOG.info(
                "shared_cost.notification_skipped",
                reason="no notification service wired",
                upload_id=str(upload.id),
            )
            return

        # Build amount lookup maps for context
        prev_totals = _aggregate_by_unit(prev_lines)
        new_totals = _aggregate_by_unit(new_lines)

        for org_unit_id in affected_unit_ids:
            try:
                manager = await _resolve_manager(org_unit_id, self._db)
                if manager is None:
                    _LOG.warning(
                        "shared_cost.no_manager_found",
                        org_unit_id=str(org_unit_id),
                    )
                    continue

                email = _extract_email(manager)
                if email is None:
                    _LOG.warning(
                        "shared_cost.manager_no_email",
                        org_unit_id=str(org_unit_id),
                        manager_id=str(manager.id),
                    )
                    continue

                prev_amt = prev_totals.get(org_unit_id, Decimal("0"))
                new_amt = new_totals.get(org_unit_id, Decimal("0"))
                delta = new_amt - prev_amt

                context: dict[str, Any] = {
                    "version": upload.version,
                    "cycle_id": str(cycle_id),
                    "prev_amount": str(prev_amt),
                    "new_amount": str(new_amt),
                    "delta": str(delta),
                }

                await self._notifications.send(
                    template=NotificationTemplate.SHARED_COST_IMPORTED,
                    recipient_user_id=manager.id,
                    recipient_email=email,
                    context=context,
                    related=("shared_cost_upload", upload.id),
                )
            except (AppError, InfraError) as exc:
                # CR-029: notification failure does NOT invalidate import
                _LOG.warning(
                    "shared_cost.notification_failed",
                    org_unit_id=str(org_unit_id),
                    upload_id=str(upload.id),
                    error=str(exc),
                )


# ============================================================
#               Module-level pure / DB helpers
# ============================================================


def _build_lines_data(
    rows: list[dict[str, Any]],
    code_id_map: dict[str, UUID],
) -> list[dict[str, Any]]:
    """Translate validated rows into line dicts with resolved UUIDs.

    Args:
        rows: Validated row dicts from :class:`SharedCostImportValidator`.
        code_id_map: ``{account_code: UUID}`` resolved from ``account_codes``.

    Returns:
        list[dict[str, Any]]: Dicts with ``org_unit_id``, ``account_code_id``,
        ``amount``.
    """
    result: list[dict[str, Any]] = []
    for row in rows:
        code = str(row["account_code"])
        account_code_id = code_id_map.get(code)
        if account_code_id is None:
            # Reason: defensive — code was validated against shared_cost_codes
            # set. If it's missing from code_id_map, the account master was
            # mutated mid-request. Skip gracefully; DB constraint will catch it.
            _LOG.warning("shared_cost.account_code_not_in_map", code=code)
            continue
        result.append(
            {
                "org_unit_id": row["org_unit_id"],
                "account_code_id": account_code_id,
                "amount": row["amount"],
            }
        )
    return result


def _ephemeral_lines(lines_data: list[dict[str, Any]]) -> list[SharedCostLine]:
    """Construct ephemeral (not-yet-persisted) SharedCostLine objects.

    Used by :func:`diff_affected_units` before the persisting transaction so
    the diff computation works on Python objects, not committed DB rows.

    Args:
        lines_data: Pre-resolved line dicts.

    Returns:
        list[SharedCostLine]: Ephemeral ORM instances (no id set).
    """
    lines: list[SharedCostLine] = []
    upload_placeholder = uuid4()
    for data in lines_data:
        line = SharedCostLine(
            upload_id=upload_placeholder,
            org_unit_id=data["org_unit_id"],
            account_code_id=data["account_code_id"],
            amount=data["amount"],
        )
        lines.append(line)
    return lines


def _aggregate_by_unit(lines: list[SharedCostLine]) -> dict[UUID, Decimal]:
    """Aggregate line amounts by org_unit_id.

    Args:
        lines: SharedCostLine rows.

    Returns:
        dict[UUID, Decimal]: Summed amounts per org unit.
    """
    totals: dict[UUID, Decimal] = {}
    for line in lines:
        totals[line.org_unit_id] = totals.get(line.org_unit_id, Decimal("0")) + line.amount
    return totals


async def _fetch_lines(
    db: AsyncSession,
    *,
    upload_id: UUID,
) -> list[SharedCostLine]:
    """Return all lines for a given upload.

    Args:
        db: Active async session.
        upload_id: Target :class:`SharedCostUpload` UUID.

    Returns:
        list[SharedCostLine]: All lines for the upload.
    """
    stmt = select(SharedCostLine).where(SharedCostLine.upload_id == upload_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


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
        dict[str, UUID]: Mapping; unknown codes are absent.
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


async def _resolve_manager(
    org_unit_id: UUID,
    db: AsyncSession,
) -> User | None:
    """Walk the org-unit parent chain to find a manager user.

    Searches for a user whose ``org_unit_id`` matches any ancestor (including
    the unit itself) and has a managerial role (FinanceAdmin, HRAdmin,
    FilingUnitManager, UplineReviewer, SystemAdmin). Returns the first match
    walking up from ``org_unit_id``. Returns ``None`` if no manager is found.

    Args:
        org_unit_id: Starting org unit UUID.
        db: Active async session.

    Returns:
        User | None: Manager user, or ``None`` when not found.
    """
    visited: set[UUID] = set()
    current_id: UUID | None = org_unit_id
    while current_id is not None and current_id not in visited:
        visited.add(current_id)
        # Find a user assigned to this org unit
        stmt = select(User).where(
            User.org_unit_id == current_id,
            User.is_active.is_(True),
        )
        result = await db.execute(stmt)
        user = result.scalars().first()
        if user is not None:
            return user
        # Walk up to parent
        unit = await db.get(OrgUnit, current_id)
        if unit is None:
            break
        current_id = unit.parent_id
    return None


async def _resolve_unit_codes(
    db: AsyncSession,
    unit_ids: list[UUID],
) -> list[str]:
    """Resolve a list of org_unit UUIDs to their codes.

    Args:
        db: Active async session.
        unit_ids: List of org unit UUIDs.

    Returns:
        list[str]: Corresponding org unit codes (in no guaranteed order).
    """
    if not unit_ids:
        return []
    stmt = select(OrgUnit.code).where(OrgUnit.id.in_(unit_ids))
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


def _extract_email(user: User) -> str | None:
    """Best-effort email decode for notification dispatch.

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
