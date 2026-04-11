"""FastAPI routes for the audit log (FR-023).

Thin orchestration only — every piece of business logic lives in
:class:`app.domain.audit.service.AuditService`. The router exposes:

* ``GET /audit-logs`` — filtered + paginated query.
* ``GET /audit-logs/verify`` — re-hash the stored chain and return a
  :class:`ChainVerificationResponse`.
* ``GET /audit-logs/export`` — CSV download of a filtered range.

All three routes are scoped to the ``ITSecurityAuditor`` role. Batch 1
ships before ``app.core.security.rbac``, so the RBAC dependency is
imported optionally — when the real module is not importable (Batch 1
runtime), ``require_role(...)`` is a no-op dependency that lets the
request through. Batch 2 will wire the real dependency.
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit.repo import AuditFilters
from app.domain.audit.service import (
    AuditLogRead,
    AuditLogsPage,
    AuditService,
    ChainVerification,
)
from app.infra.db.session import get_session

# --- RBAC dependency stub -------------------------------------------------
# Batch 2 will wire real RBAC via ``app.core.security.rbac.require_role``.
try:  # pragma: no cover — exercised in Batch 2
    from app.core.security.rbac import Role, require_role  # type: ignore[import-not-found]
except ImportError:

    class Role:  # type: ignore[no-redef]
        """Batch 1 placeholder — Batch 2 ships the real :class:`Role` enum."""

        ITSecurityAuditor = "ITSecurityAuditor"

    def require_role(*_roles: Any) -> Callable[[], None]:  # type: ignore[no-redef]
        """Batch 1 placeholder RBAC dependency — Batch 2 will wire real RBAC.

        Args:
            *_roles: Role names accepted by the real dependency (ignored here).

        Returns:
            Callable[[], None]: A no-op FastAPI dependency.
        """

        def _noop() -> None:
            """Allow the request through unconditionally (Batch 1 only)."""
            return None

        return _noop


__all__ = ["ChainVerificationResponse", "router"]


router = APIRouter(prefix="/audit-logs", tags=["audit"])


class ChainVerificationResponse(BaseModel):
    """Response body for ``GET /audit-logs/verify``.

    Mirrors architecture §5.11 shape verbatim:
    ``{"verified": true, "range": [iso, iso], "chain_length": N}``.
    """

    verified: bool
    range: list[datetime | None]
    chain_length: int


@router.get("", response_model=AuditLogsPage)
async def list_audit_logs(
    user_id: UUID | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: UUID | None = Query(None),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _user: None = Depends(require_role(Role.ITSecurityAuditor)),
) -> AuditLogsPage:
    """Query audit logs with optional filters and pagination.

    Args:
        user_id: Filter to a specific user.
        action: Filter to a specific :class:`AuditAction` value.
        resource_type: Filter to a resource type.
        resource_id: Filter to a specific resource UUID.
        from_: Start of ``occurred_at`` range (UTC).
        to: End of ``occurred_at`` range (UTC).
        page: Page number (1-based).
        size: Page size (max 200).
        db: Database session from FastAPI dependency.
        _user: RBAC guard (Batch 1 stub; Batch 2 wires real RBAC).

    Returns:
        AuditLogsPage: Paginated audit log items.
    """
    del _user  # Reason: RBAC guard is applied via Depends; value is unused.
    filters = AuditFilters(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        from_dt=from_,
        to_dt=to,
        page=page,
        size=size,
    )
    service = AuditService(db)
    result = await service.query(filters)
    return AuditLogsPage(
        items=[AuditLogRead.model_validate(row) for row in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
    )


@router.get("/verify", response_model=ChainVerificationResponse)
async def verify_audit_chain(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user: None = Depends(require_role(Role.ITSecurityAuditor)),
) -> ChainVerificationResponse:
    """Verify the audit log hash chain for a date range.

    Args:
        from_: Start of verification range (UTC).
        to: End of verification range (UTC).
        db: Database session from FastAPI dependency.
        _user: RBAC guard (Batch 1 stub).

    Returns:
        ChainVerificationResponse: Verification result with range and chain length.

    Raises:
        AppError: code=``AUDIT_001`` (HTTP 500) if any row fails to verify.
    """
    del _user
    service = AuditService(db)
    result: ChainVerification = await service.verify_chain(from_, to)
    return ChainVerificationResponse(
        verified=result.verified,
        range=[result.range_start, result.range_end],
        chain_length=result.chain_length,
    )


@router.get("/export")
async def export_audit_logs(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user: None = Depends(require_role(Role.ITSecurityAuditor)),
) -> StreamingResponse:
    """Export filtered audit log rows as a streamed CSV download.

    Args:
        from_: Start of range (UTC).
        to: End of range (UTC).
        db: Database session from FastAPI dependency.
        _user: RBAC guard (Batch 1 stub).

    Returns:
        StreamingResponse: CSV file download with
        ``Content-Disposition: attachment; filename=audit_logs.csv``.
    """
    del _user
    service = AuditService(db)
    rows = await service._repo.fetch_range(from_, to)

    async def _iter_csv() -> AsyncIterator[str]:
        """Yield CSV header + rows as a stream of strings."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "sequence_no",
                "occurred_at",
                "user_id",
                "action",
                "resource_type",
                "resource_id",
                "ip_address",
                "details",
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
        for row in rows:
            writer.writerow(
                [
                    row.sequence_no,
                    row.occurred_at.isoformat() if row.occurred_at else "",
                    str(row.user_id) if row.user_id else "",
                    row.action,
                    row.resource_type,
                    str(row.resource_id) if row.resource_id else "",
                    row.ip_address or "",
                    row.details,
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()

    return StreamingResponse(
        _iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
