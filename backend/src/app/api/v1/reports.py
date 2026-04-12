"""FastAPI routes for the consolidated report + export endpoints (FR-015..017).

Thin orchestration — every piece of business logic lives in
:class:`app.domain.consolidation.report.ConsolidatedReportService` and
:class:`app.domain.consolidation.export.ReportExportService`. The route
layer resolves the RBAC-scoped org unit set and hands it down as a
:class:`ReportScope`.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.consolidation.export import ExportEnqueueResult, ReportExportService
from app.domain.consolidation.report import ConsolidatedReport, ConsolidatedReportService
from app.infra import jobs as jobs_module
from app.infra import storage as storage_module
from app.infra.db.session import get_session

__all__ = ["router"]


router = APIRouter(tags=["reports"])


def _build_report_service(db: AsyncSession) -> ConsolidatedReportService:
    """Return a :class:`ConsolidatedReportService` bound to ``db``.

    Args:
        db: Active session.

    Returns:
        ConsolidatedReportService: Fresh service.
    """
    return ConsolidatedReportService(db)


def _build_export_service(db: AsyncSession) -> ReportExportService:
    """Return a :class:`ReportExportService` bound to ``db``.

    Args:
        db: Active session.

    Returns:
        ReportExportService: Fresh service.
    """
    return ReportExportService(db)


@router.get(
    "/cycles/{cycle_id}/reports/consolidated",
    response_model=ConsolidatedReport,
)
async def get_consolidated_report(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.SystemAdmin,
            Role.FinanceAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
        )
    ),
) -> ConsolidatedReport:
    """Return the consolidated report for ``cycle_id`` scoped to ``user``.

    Args:
        cycle_id: Target cycle id.
        db: Injected DB session.
        user: Authenticated caller.

    Returns:
        ConsolidatedReport: Joined budget/personnel/shared-cost view.
    """
    service = _build_report_service(db)
    scope = await service.resolve_scope(user=user)
    return await service.build(cycle_id=cycle_id, scope=scope)


@router.post("/cycles/{cycle_id}/reports/exports")
async def start_report_export(
    cycle_id: UUID,
    export_format: Literal["xlsx", "csv"] = Query(default="xlsx", alias="format"),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.SystemAdmin,
            Role.FinanceAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
        )
    ),
) -> JSONResponse:
    """Start a report export (sync or async depending on scope size).

    Args:
        cycle_id: Target cycle id.
        export_format: Output format — ``xlsx`` or ``csv``.
        db: Injected DB session.
        user: Authenticated caller.

    Returns:
        JSONResponse: ``201`` with ``file_url`` (sync path) or ``202``
        with ``job_id`` (async path).
    """
    report_service = _build_report_service(db)
    export_service = _build_export_service(db)
    scope = await report_service.resolve_scope(user=user)
    result = await export_service.export_async(
        cycle_id=cycle_id,
        scope=scope,
        export_format=export_format,
        user=user,
    )
    status_code = 201 if result.mode == "sync" else 202
    return JSONResponse(
        status_code=status_code,
        content=_enqueue_result_to_dict(result),
    )


@router.get("/exports/{job_id}")
async def get_export_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(
        require_role(
            Role.SystemAdmin,
            Role.FinanceAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
        )
    ),
) -> dict[str, object]:
    """Return the durable-job status for an async export.

    Args:
        job_id: Job run id returned by :func:`start_report_export`.
        db: Injected DB session.
        _user: Authenticated caller.

    Returns:
        dict[str, object]: Job metadata (``status``, ``result``,
        ``error_message``, ...).
    """
    del _user
    status = await jobs_module.get_status(job_id, db)
    return {
        k: (str(v) if not isinstance(v, (int, float, str, dict, list, type(None))) else v)
        for k, v in status.items()
    }


@router.get("/exports/{job_id}/file")
async def download_export_file(
    job_id: UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(
        require_role(
            Role.SystemAdmin,
            Role.FinanceAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
        )
    ),
) -> Response:
    """Stream the exported file bytes for a completed async export.

    Args:
        job_id: Job run id.
        db: Injected DB session.
        _user: Authenticated caller.

    Returns:
        Response: Raw bytes with the appropriate content-type.

    Raises:
        NotFoundError: ``REPORT_001`` if the job is not complete.
    """
    del _user
    status = await jobs_module.get_status(job_id, db)
    if status.get("status") != "completed":
        raise NotFoundError("REPORT_001", "Export job is not complete")
    result = status.get("result") or {}
    storage_key = result.get("file_url") if isinstance(result, dict) else None
    if not storage_key:
        raise NotFoundError("REPORT_001", "Export has no file_url")
    try:
        content = await storage_module.read(str(storage_key))
    except AppError as exc:
        raise NotFoundError("REPORT_001", f"Export file missing: {exc.code}") from exc
    media_type = (
        "text/csv"
        if str(storage_key).endswith(".csv")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return Response(content=content, media_type=media_type)


def _enqueue_result_to_dict(result: ExportEnqueueResult) -> dict[str, object]:
    """Serialize :class:`ExportEnqueueResult` for the JSON response.

    Args:
        result: Source payload.

    Returns:
        dict[str, object]: JSON-safe dict.
    """
    return {
        "mode": result.mode,
        "file_url": result.file_url,
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "job_id": str(result.job_id) if result.job_id else None,
    }
