"""Report export service + job handler (FR-017).

Owns the sync/async dispatch for consolidated report exports. When the
scoped unit count is ``<= BC_ASYNC_EXPORT_THRESHOLD``, the workbook is
built and saved synchronously — the caller receives a sync result with
the signed storage URL. Otherwise, a durable job is enqueued via
:mod:`app.infra.jobs` and the caller receives an async result with the
``job_id``.

Both paths record a ``REPORT_EXPORT_QUEUED`` audit event (CR-006 — after
the workbook is persisted on the sync path).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import AppError, InfraError
from app.core.security.models import User
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.consolidation.report import (
    ConsolidatedReport,
    ConsolidatedReportRow,
    ConsolidatedReportService,
    ReportScope,
)
from app.domain.cycles.models import BudgetCycle
from app.domain.notifications.templates import NotificationTemplate
from app.infra import jobs as jobs_module
from app.infra import storage as storage_module
from app.infra.excel import workbook_to_bytes, write_workbook

__all__ = [
    "ExportEnqueueResult",
    "ReportExportHandler",
    "ReportExportService",
    "register_report_export_handler",
]


_LOG = structlog.get_logger(__name__)


class ExportEnqueueResult(BaseModel):
    """Return value of :meth:`ReportExportService.export_async`.

    Attributes:
        mode: ``"sync"`` for immediate storage write, ``"async"`` when a
            durable job was enqueued instead.
        file_url: Signed / relative URL of the exported file (sync
            only).
        expires_at: Expiry timestamp for ``file_url`` (sync only).
        job_id: Job run id returned by :func:`infra.jobs.enqueue` (async
            only).
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["sync", "async"]
    file_url: str | None = None
    expires_at: datetime | None = None
    job_id: UUID | None = None


class ReportExportService:
    """Thin facade that dispatches export requests to the right path.

    The service is request-scoped (accepts an :class:`AsyncSession` at
    construction). Collaborators (report builder, audit, notifications)
    are built lazily from that session.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        report_service: ConsolidatedReportService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            db: Active :class:`AsyncSession`.
            report_service: Optional pre-wired report service. Tests
                inject a fake.
            audit_service: Optional pre-wired audit service.
        """
        self._db = db
        self._report = (
            report_service if report_service is not None else ConsolidatedReportService(db)
        )
        self._audit = audit_service if audit_service is not None else AuditService(db)

    async def export_async(
        self,
        *,
        cycle_id: UUID,
        scope: ReportScope,
        export_format: Literal["xlsx", "csv"],
        user: User,
    ) -> ExportEnqueueResult:
        """Run the sync or async export path depending on scope size.

        Args:
            cycle_id: Target cycle id.
            scope: RBAC-resolved scope (from
                :meth:`ConsolidatedReportService.resolve_scope`).
            export_format: ``"xlsx"`` or ``"csv"``.
            user: Caller (used for audit + async notification context).

        Returns:
            ExportEnqueueResult: Sync result with ``file_url`` or async
            result with ``job_id``.

        Raises:
            AppError: ``REPORT_002`` on any synchronous build failure.
        """
        settings = get_settings()
        threshold = settings.async_export_threshold
        scope_size = 0 if scope.all_scopes else len(scope.org_unit_ids)

        if scope.all_scopes or scope_size > threshold:
            return await self._enqueue_async(
                cycle_id=cycle_id,
                scope=scope,
                export_format=export_format,
                user=user,
            )
        return await self._run_sync(
            cycle_id=cycle_id,
            scope=scope,
            export_format=export_format,
            user=user,
        )

    async def _run_sync(
        self,
        *,
        cycle_id: UUID,
        scope: ReportScope,
        export_format: Literal["xlsx", "csv"],
        user: User,
    ) -> ExportEnqueueResult:
        """Build the workbook synchronously, save bytes, and audit.

        Args:
            cycle_id: Target cycle id.
            scope: Caller scope.
            export_format: Output format.
            user: Caller.

        Returns:
            ExportEnqueueResult: ``mode='sync'`` with file URL and
            expiry.

        Raises:
            AppError: ``REPORT_002`` on any failure in the sync path.
        """
        try:
            report = await self._report.build(cycle_id=cycle_id, scope=scope)
            filename, content = _render_report(report=report, export_format=export_format)
            storage_key = await storage_module.save(
                category="exports",
                filename=filename,
                content=content,
            )
        except AppError:
            raise
        except Exception as exc:
            _LOG.error(
                "report_export.sync_failed",
                cycle_id=str(cycle_id),
                error=str(exc),
            )
            raise AppError("REPORT_002", f"Report export failed: {exc}") from exc

        expires_at = now_utc() + timedelta(hours=24)

        # CR-006: audit AFTER the workbook is persisted.
        await self._audit.record(
            action=AuditAction.REPORT_EXPORT_QUEUED,
            resource_type="report_export",
            resource_id=None,
            user_id=user.id,
            details={
                "cycle_id": str(cycle_id),
                "mode": "sync",
                "format": export_format,
                "row_count": len(report.rows),
                "storage_key": storage_key,
            },
        )

        return ExportEnqueueResult(
            mode="sync",
            file_url=storage_key,
            expires_at=expires_at,
            job_id=None,
        )

    async def _enqueue_async(
        self,
        *,
        cycle_id: UUID,
        scope: ReportScope,
        export_format: Literal["xlsx", "csv"],
        user: User,
    ) -> ExportEnqueueResult:
        """Enqueue a durable job and record the queued audit event.

        Args:
            cycle_id: Target cycle id.
            scope: Caller scope.
            export_format: Output format.
            user: Caller.

        Returns:
            ExportEnqueueResult: ``mode='async'`` with ``job_id``.
        """
        payload = {
            "cycle_id": str(cycle_id),
            "scope_all": scope.all_scopes,
            "scope_org_unit_ids": sorted(str(uid) for uid in scope.org_unit_ids),
            "format": export_format,
            "user_id": str(user.id),
        }
        job_id = await jobs_module.enqueue(
            "report_export",
            payload,
            db=self._db,
            user_id=user.id,
        )
        await self._audit.record(
            action=AuditAction.REPORT_EXPORT_QUEUED,
            resource_type="job_run",
            resource_id=job_id,
            user_id=user.id,
            details={
                "cycle_id": str(cycle_id),
                "mode": "async",
                "format": export_format,
            },
        )
        return ExportEnqueueResult(
            mode="async",
            file_url=None,
            expires_at=None,
            job_id=job_id,
        )


class ReportExportHandler:
    """Durable-job handler for ``report_export`` tasks.

    Constructed at application startup with a session factory and an
    email-sender factory. The handler reopens its own session per job
    run so it does not inherit request-scoped state. Registered with
    :func:`app.infra.jobs.register_handler` via
    :func:`register_report_export_handler`.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        notification_factory: Any,
    ) -> None:
        """Initialize the handler.

        Args:
            session_factory: :func:`async_sessionmaker` used to open a
                fresh :class:`AsyncSession` per job run.
            notification_factory: Callable ``(db) -> NotificationService``
                that constructs a per-run notification service.
        """
        self._session_factory = session_factory
        self._notification_factory = notification_factory

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a queued report-export job.

        Args:
            payload: Dict produced by
                :meth:`ReportExportService._enqueue_async`.

        Returns:
            dict[str, Any]: ``{'file_url', 'expires_at', 'row_count'}``
            on success.

        Raises:
            AppError: ``REPORT_002`` on any failure during build or
                save.
        """
        cycle_id = UUID(str(payload["cycle_id"]))
        export_format = str(payload.get("format", "xlsx"))
        user_id = UUID(str(payload["user_id"]))
        scope_all = bool(payload.get("scope_all", False))
        raw_ids_raw: object = payload.get("scope_org_unit_ids") or []
        raw_ids: list[str] = _coerce_uuid_strings(raw_ids_raw)
        scope = ReportScope(
            user_id=user_id,
            org_unit_ids=frozenset(UUID(uid) for uid in raw_ids),
            all_scopes=scope_all,
        )

        async with self._session_factory() as session:
            try:
                report_service = ConsolidatedReportService(session)
                report = await report_service.build(cycle_id=cycle_id, scope=scope)
                filename, content = _render_report(
                    report=report,
                    export_format=export_format,  # type: ignore[arg-type]
                )
                storage_key = await storage_module.save(
                    category="exports",
                    filename=filename,
                    content=content,
                )
            except AppError:
                raise
            except Exception as exc:
                raise AppError("REPORT_002", f"Report export failed: {exc}") from exc

            expires_at = now_utc() + timedelta(hours=24)
            row_count = len(report.rows)

            # Audit completion + fan out email notification.
            audit = AuditService(session)
            await audit.record(
                action=AuditAction.REPORT_EXPORT_COMPLETE,
                resource_type="report_export",
                resource_id=None,
                user_id=user_id,
                details={
                    "cycle_id": str(cycle_id),
                    "row_count": row_count,
                    "storage_key": storage_key,
                },
            )
            await session.commit()

            await self._send_notification(
                session=session,
                user_id=user_id,
                cycle_id=cycle_id,
                file_url=storage_key,
                row_count=row_count,
                expires_at=expires_at,
            )

        return {
            "file_url": storage_key,
            "expires_at": expires_at.isoformat(),
            "row_count": row_count,
        }

    async def _send_notification(
        self,
        *,
        session: AsyncSession,
        user_id: UUID,
        cycle_id: UUID,
        file_url: str,
        row_count: int,
        expires_at: datetime,
    ) -> None:
        """Send the REPORT_EXPORT_READY email to the requester.

        Best-effort: SMTP failures are already isolated by
        :meth:`NotificationService.send` (CR-029).

        Args:
            session: Active session used to resolve the user row.
            user_id: UUID of the recipient.
            cycle_id: Cycle the export was built for.
            file_url: Signed storage URL / key.
            row_count: Row count for the rendered report.
            expires_at: Expiry timestamp for the link.
        """
        notification_service = self._notification_factory(session)
        if notification_service is None:
            return
        user = await session.get(User, user_id)
        if user is None:
            return
        cycle = await session.get(BudgetCycle, cycle_id)
        email = _extract_email(user)
        if email is None:
            return
        context: dict[str, Any] = {
            "cycle_fiscal_year": cycle.fiscal_year if cycle is not None else None,
            "file_url": file_url,
            "row_count": row_count,
            "expires_at": expires_at.isoformat(),
        }
        try:
            await notification_service.send(
                template=NotificationTemplate.REPORT_EXPORT_READY,
                recipient_user_id=user_id,
                recipient_email=email,
                context=context,
            )
        except (InfraError, AppError) as exc:
            _LOG.warning(
                "report_export.notification_failed",
                user_id=str(user_id),
                error=exc.code,
            )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _render_report(
    *,
    report: ConsolidatedReport,
    export_format: Literal["xlsx", "csv"],
) -> tuple[str, bytes]:
    """Serialize ``report`` to the requested ``export_format``.

    Args:
        report: Source report.
        export_format: ``"xlsx"`` or ``"csv"``.

    Returns:
        tuple[str, bytes]: ``(filename, content_bytes)``.
    """
    if export_format == "csv":
        return _render_csv(report)
    return _render_xlsx(report)


_COLUMNS: tuple[str, ...] = (
    "org_unit_id",
    "org_unit_name",
    "account_code",
    "account_name",
    "actual",
    "operational_budget",
    "personnel_budget",
    "shared_cost",
    "delta_amount",
    "delta_pct",
    "budget_status",
)


def _render_xlsx(report: ConsolidatedReport) -> tuple[str, bytes]:
    """Render ``report`` as a minimal ``.xlsx`` workbook.

    Args:
        report: Source report.

    Returns:
        tuple[str, bytes]: Filename + workbook bytes.
    """
    workbook = write_workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "consolidated"
    for col_idx, column in enumerate(_COLUMNS, start=1):
        sheet.cell(row=1, column=col_idx, value=column)
    for row_idx, row in enumerate(report.rows, start=2):
        for col_idx, column in enumerate(_COLUMNS, start=1):
            value = _row_value(row=row, column=column)
            sheet.cell(row=row_idx, column=col_idx, value=value)
    content = workbook_to_bytes(workbook)
    filename = f"consolidated_{report.cycle_id}.xlsx"
    return filename, content


def _render_csv(report: ConsolidatedReport) -> tuple[str, bytes]:
    """Render ``report`` as CSV bytes.

    Args:
        report: Source report.

    Returns:
        tuple[str, bytes]: Filename + CSV bytes.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_COLUMNS)
    for row in report.rows:
        writer.writerow([_row_value(row=row, column=column) for column in _COLUMNS])
    filename = f"consolidated_{report.cycle_id}.csv"
    return filename, buf.getvalue().encode("utf-8")


def _row_value(*, row: ConsolidatedReportRow, column: str) -> Any:
    """Return the cell value for ``row[column]``.

    Args:
        row: Source row.
        column: Column name (one of :data:`_COLUMNS`).

    Returns:
        Any: Stringified-Decimal / UUID / raw value suitable for
        workbook and CSV writers.
    """
    value = getattr(row, column)
    if value is None:
        return ""
    if isinstance(value, UUID):
        return str(value)
    return str(value) if not isinstance(value, (int, float, str)) else value


def _coerce_uuid_strings(value: object) -> list[str]:
    """Return a best-effort list of UUID-coerced strings from ``value``.

    Args:
        value: Arbitrary JSON payload value.

    Returns:
        list[str]: Stringified entries when ``value`` is a list, else
        an empty list.
    """
    if not isinstance(value, list):
        return []
    out: list[str] = []
    entries: list[Any] = value  # type: ignore[assignment]
    for entry in entries:
        out.append(str(entry))
    return out


def _extract_email(user: User) -> str | None:
    """Decode a plaintext email address from a :class:`User` row.

    Mirrors the helper in :mod:`app.domain.budget_uploads.service`.

    Args:
        user: User whose email is being resolved.

    Returns:
        str | None: Decoded email or ``None`` when decoding fails.
    """
    raw = user.email_enc or b""
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if "@" in text else None


def register_report_export_handler(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    notification_factory: Any,
) -> None:
    """Register the ``report_export`` handler with :mod:`app.infra.jobs`.

    Called from the FastAPI lifespan on startup.

    Args:
        session_factory: Async sessionmaker for per-run DB sessions.
        notification_factory: Callable returning a
            :class:`NotificationService` bound to the supplied session.
    """
    handler = ReportExportHandler(
        session_factory=session_factory,
        notification_factory=notification_factory,
    )
    jobs_module.register_handler("report_export", handler.run)
