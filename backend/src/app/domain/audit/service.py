"""Audit log service — hash-chain writer and verifier (FR-023, CR-031).

Hash chain payload serialization (**CR-031**, verbatim from the spec)
----------------------------------------------------------------------

Every audit row's hash is computed over a **canonical** JSON blob produced
by :meth:`AuditService._serialize_for_chain`. The exact serialization is:

.. code-block:: python

    payload = {
        "sequence_no": row.sequence_no,
        "user_id": str(row.user_id) if row.user_id else None,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id) if row.resource_id else None,
        "ip_address": row.ip_address,
        "details": row.details,
        "occurred_at": row.occurred_at.isoformat(),  # must include +00:00 for UTC
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

Rules (verbatim from CR-031):

* JSON keys sorted (``sort_keys=True``).
* Separators ``(",", ":")`` — no extra whitespace.
* Datetimes serialized via :meth:`datetime.isoformat` after normalizing to
  UTC (``tzinfo=timezone.utc``); the ``+00:00`` suffix is required so that
  future auditors can re-verify the chain independently.
* The UUID fields are stringified (lowercase hex-dashed form). ``None``
  passes through.
* Both :meth:`record` and :meth:`verify_chain` use this single helper —
  the serialization logic is never duplicated.

Any drift between writer and verifier — even a single whitespace
difference — breaks the chain. Do not refactor :meth:`_serialize_for_chain`
without running ``verify_chain`` against a known-good fixture first.

Commit sequencing (**CR-006**)
------------------------------

:meth:`AuditService.record` runs INSIDE the caller's transaction. Per
CR-006, calling services must:

1. Commit the main state change first (``await db.commit()``).
2. Call ``await audit_service.record(...)``.
3. Commit the audit row (``await db.commit()``).
4. Return.

This module does not commit on the caller's behalf.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.errors import AppError
from app.domain.audit.actions import AuditAction
from app.domain.audit.models import AuditLog
from app.domain.audit.repo import AuditFilters, AuditRepo, Page
from app.infra.crypto import chain_hash

__all__ = [
    "AuditFilters",
    "AuditLogRead",
    "AuditLogsPage",
    "AuditService",
    "ChainVerification",
    "Page",
]


# 32-byte genesis sentinel for the very first row's prev_hash.
_GENESIS_PREV_HASH: bytes = b"\x00" * 32


# --------------------------------------------------------------------------- schemas
class AuditLogRead(BaseModel):
    """Pydantic read model for a single audit log row.

    Shape matches the architecture §5.11 response contract exactly — the
    field keys are what the ``GET /audit-logs`` endpoint serializes into
    its ``items`` array.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime = Field(validation_alias="occurred_at")
    user_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    ip_address: str | None
    details: dict[str, Any]


class AuditLogsPage(BaseModel):
    """Response model for the ``GET /audit-logs`` endpoint."""

    items: list[AuditLogRead]
    total: int
    page: int
    size: int


@dataclass
class ChainVerification:
    """Result of a hash-chain verification.

    Attributes:
        verified (bool): ``True`` iff all rows in range passed the hash check.
        range_start (datetime | None): Start of the verified range (inclusive).
        range_end (datetime | None): End of the verified range (inclusive).
        chain_length (int): Number of rows checked.
        failed_at_sequence_no (int | None): ``sequence_no`` of the first
            failed row, or ``None`` when every row verified cleanly.
    """

    verified: bool
    range_start: datetime | None
    range_end: datetime | None
    chain_length: int
    failed_at_sequence_no: int | None


# --------------------------------------------------------------------------- service
class AuditService:
    """Write and query the append-only audit log.

    Owns the hash chain advancement logic. Delegates read access to
    :class:`AuditRepo`. Never commits on the caller's behalf.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active async DB session.

        Args:
            db (AsyncSession): Active async session managed by the caller.
        """
        self._db = db
        self._repo = AuditRepo(db)

    async def record(
        self,
        *,
        action: AuditAction,
        resource_type: str,
        resource_id: UUID | None = None,
        user_id: UUID | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Append a new audit log row with hash-chain advancement.

        Steps:

        1. Fetch the latest row (or use the 32-byte zero sentinel for the
           genesis row) to obtain ``prev_hash``.
        2. Build the :class:`AuditLog` ORM instance with an explicit UTC
           ``occurred_at`` derived from :func:`app.core.clock.now_utc`.
        3. Insert the row via :meth:`AuditRepo.insert` (flush-only) so the
           DB assigns ``sequence_no``.
        4. Serialize the row with :meth:`_serialize_for_chain` and compute
           ``hash_chain_value = chain_hash(prev_hash, payload)``.
        5. Write ``hash_chain_value`` back onto the row and flush again.

        This method does NOT commit. Per CR-006, the calling service must
        commit its own state change first and then call ``record``, and is
        responsible for committing the audit row afterwards.

        Args:
            action (AuditAction): Enum member — never a raw string (CR-002).
            resource_type (str): Resource type (e.g. ``"cycle"``).
            resource_id (UUID | None): Resource UUID, or ``None``.
            user_id (UUID | None): Acting user's id, or ``None`` for system events.
            ip_address (str | None): Request IP address.
            details (dict[str, Any] | None): Event-specific metadata (JSONB).

        Returns:
            AuditLog: The newly inserted :class:`AuditLog` ORM instance with
            ``sequence_no`` and ``hash_chain_value`` populated.
        """
        prev_row = await self._repo.get_latest()
        prev_hash = prev_row.hash_chain_value if prev_row is not None else _GENESIS_PREV_HASH

        row = AuditLog(
            user_id=user_id,
            action=str(action.value),
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            details=dict(details) if details is not None else {},
            prev_hash=prev_hash,
            # Placeholder — replaced after sequence_no is assigned by the DB.
            hash_chain_value=_GENESIS_PREV_HASH,
            occurred_at=now_utc(),
        )

        await self._repo.insert(row)

        payload = self._serialize_for_chain(row)
        row.hash_chain_value = chain_hash(prev_hash, payload)
        await self._db.flush()
        return row

    async def query(self, filters: AuditFilters) -> Page[AuditLog]:
        """Return a filtered, paginated page of audit log rows.

        Args:
            filters (AuditFilters): Query filters including pagination.

        Returns:
            Page[AuditLog]: Paginated audit log results.

        Raises:
            AppError: code=``AUDIT_002`` when filter params are invalid.
        """
        return await self._repo.fetch_page(filters)

    async def verify_chain(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> ChainVerification:
        """Re-compute the hash chain for a range and compare to stored values.

        Fetches rows in ``sequence_no`` order, re-serializes each with
        :meth:`_serialize_for_chain`, recomputes
        ``chain_hash(prev_hash, payload)`` and compares it to the stored
        ``hash_chain_value``. The first mismatch raises ``AUDIT_001`` per
        FR-023 strict mode.

        Args:
            start (datetime | None): Start of range (``occurred_at`` inclusive).
                ``None`` starts from the first row.
            end (datetime | None): End of range (``occurred_at`` inclusive).
                ``None`` runs through the latest row.

        Returns:
            ChainVerification: With ``verified=True`` when every row passes.

        Raises:
            AppError: code=``AUDIT_001`` on the first row that fails to
                verify. The exception's ``details`` include the failing
                ``sequence_no`` and the expected/actual hash bytes (hex).
        """
        rows = await self._repo.fetch_range(start, end)
        if not rows:
            return ChainVerification(
                verified=True,
                range_start=start,
                range_end=end,
                chain_length=0,
                failed_at_sequence_no=None,
            )

        expected_prev = rows[0].prev_hash
        for row in rows:
            if row.prev_hash != expected_prev:
                raise AppError(
                    "AUDIT_001",
                    f"Audit chain broken at sequence_no={row.sequence_no}: prev_hash mismatch",
                    details=[
                        {
                            "sequence_no": row.sequence_no,
                            "expected_prev_hash": expected_prev.hex(),
                            "actual_prev_hash": row.prev_hash.hex(),
                        }
                    ],
                )
            payload = self._serialize_for_chain(row)
            recomputed = chain_hash(row.prev_hash, payload)
            if recomputed != row.hash_chain_value:
                raise AppError(
                    "AUDIT_001",
                    f"Audit chain broken at sequence_no={row.sequence_no}: hash mismatch",
                    details=[
                        {
                            "sequence_no": row.sequence_no,
                            "expected_hash": recomputed.hex(),
                            "actual_hash": row.hash_chain_value.hex(),
                        }
                    ],
                )
            expected_prev = row.hash_chain_value

        return ChainVerification(
            verified=True,
            range_start=start,
            range_end=end,
            chain_length=len(rows),
            failed_at_sequence_no=None,
        )

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _serialize_for_chain(row: AuditLog) -> bytes:
        """Serialize a row to the canonical JSON bytes used for hashing.

        Must produce identical output in :meth:`record` and
        :meth:`verify_chain`. Any drift breaks the chain. See the module
        docstring for the full CR-031 rules.

        Args:
            row (AuditLog): The audit log row to serialize.

        Returns:
            bytes: UTF-8 JSON with sorted keys and no extra whitespace.
        """
        occurred_at = row.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        else:
            occurred_at = occurred_at.astimezone(timezone.utc)
        payload: dict[str, Any] = {
            "sequence_no": row.sequence_no,
            "user_id": str(row.user_id) if row.user_id else None,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id) if row.resource_id else None,
            "ip_address": row.ip_address,
            "details": row.details,
            "occurred_at": occurred_at.isoformat(),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
