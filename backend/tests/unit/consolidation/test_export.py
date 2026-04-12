"""Unit tests for :class:`ReportExportService` (FR-017)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.domain.audit.actions import AuditAction
from app.domain.consolidation.export import ReportExportService
from app.domain.consolidation.report import ConsolidatedReport, ReportScope
from app.domain.cycles.models import CycleState
from tests.unit.consolidation.conftest import (
    StubSession,
    make_cycle,
    make_user,
)


class FakeReportService:
    """Stub :class:`ConsolidatedReportService` that returns a fixed report."""

    def __init__(self, report: ConsolidatedReport) -> None:
        """Initialize with the fixed report."""
        self._report = report
        self.calls: list[Any] = []

    async def resolve_scope(self, *, user: Any) -> ReportScope:
        """Return a narrow test scope."""
        return ReportScope(user_id=user.id, all_scopes=False)

    async def build(self, *, cycle_id: Any, scope: Any) -> ConsolidatedReport:
        """Return the fixed report."""
        self.calls.append({"cycle_id": cycle_id, "scope": scope})
        return self._report


class FakeAudit:
    """In-memory :class:`AuditService` stand-in."""

    def __init__(self) -> None:
        """Initialize an empty event log."""
        self.events: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        """Capture the call."""
        self.events.append(kwargs)


@pytest.fixture
def fake_report() -> ConsolidatedReport:
    """Return a tiny fixed :class:`ConsolidatedReport`."""
    return ConsolidatedReport(cycle_id=uuid4(), rows=[])


@pytest.fixture
def tmp_storage(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point :mod:`app.infra.storage` at a fresh temp directory."""
    monkeypatch.setenv("BC_STORAGE_ROOT", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    return tmp_path


@pytest.mark.asyncio
async def test_export_sync_returns_file_url(
    stub_session: StubSession,
    fake_report: ConsolidatedReport,
    tmp_storage: Any,
) -> None:
    """Scope size ≤ threshold → sync result with ``file_url``."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    user = make_user()

    fake_rpt = FakeReportService(fake_report)
    fake_audit = FakeAudit()
    service = ReportExportService(
        stub_session,  # type: ignore[arg-type]
        report_service=fake_rpt,  # type: ignore[arg-type]
        audit_service=fake_audit,  # type: ignore[arg-type]
    )

    scope = ReportScope(
        user_id=user.id,
        org_unit_ids=frozenset({uuid4()}),
        all_scopes=False,
    )
    result = await service.export_async(
        cycle_id=cycle.id,
        scope=scope,
        export_format="csv",
        user=user,
    )

    assert result.mode == "sync"
    assert result.file_url is not None
    assert result.expires_at is not None
    assert result.job_id is None
    assert any(e["action"] == AuditAction.REPORT_EXPORT_QUEUED for e in fake_audit.events)


@pytest.mark.asyncio
async def test_export_async_enqueues_job(
    stub_session: StubSession,
    fake_report: ConsolidatedReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scope size above threshold → async result with ``job_id``."""
    monkeypatch.setenv("BC_ASYNC_EXPORT_THRESHOLD", "1")
    from app.config import get_settings

    get_settings.cache_clear()

    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    user = make_user()

    # Patch infra.jobs.enqueue to avoid needing a real job_runs table.
    import app.domain.consolidation.export as export_module

    recorded_payloads: list[dict[str, Any]] = []
    fake_job_id = uuid4()

    async def _enqueue(
        job_type: str,
        payload: dict[str, Any],
        *,
        db: Any,
        user_id: Any,
    ) -> Any:
        recorded_payloads.append({"job_type": job_type, "payload": payload, "user_id": user_id})
        return fake_job_id

    monkeypatch.setattr(export_module.jobs_module, "enqueue", _enqueue)

    fake_rpt = FakeReportService(fake_report)
    fake_audit = FakeAudit()
    service = ReportExportService(
        stub_session,  # type: ignore[arg-type]
        report_service=fake_rpt,  # type: ignore[arg-type]
        audit_service=fake_audit,  # type: ignore[arg-type]
    )

    scope = ReportScope(
        user_id=user.id,
        org_unit_ids=frozenset({uuid4(), uuid4(), uuid4()}),
        all_scopes=False,
    )
    result = await service.export_async(
        cycle_id=cycle.id,
        scope=scope,
        export_format="xlsx",
        user=user,
    )

    assert result.mode == "async"
    assert result.job_id == fake_job_id
    assert result.file_url is None
    assert result.expires_at is None
    assert len(recorded_payloads) == 1
    assert recorded_payloads[0]["job_type"] == "report_export"
    assert any(e["action"] == AuditAction.REPORT_EXPORT_QUEUED for e in fake_audit.events)


@pytest.mark.asyncio
async def test_sync_failure_raises_report_002(
    stub_session: StubSession,
    fake_report: ConsolidatedReport,
    tmp_storage: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any sync path failure maps to ``AppError('REPORT_002')``."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    user = make_user()

    fake_rpt = FakeReportService(fake_report)
    fake_audit = FakeAudit()
    service = ReportExportService(
        stub_session,  # type: ignore[arg-type]
        report_service=fake_rpt,  # type: ignore[arg-type]
        audit_service=fake_audit,  # type: ignore[arg-type]
    )

    import app.domain.consolidation.export as export_module

    async def _bad_save(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("disk full")

    monkeypatch.setattr(export_module.storage_module, "save", _bad_save)

    scope = ReportScope(
        user_id=user.id,
        org_unit_ids=frozenset({uuid4()}),
        all_scopes=False,
    )
    with pytest.raises(AppError) as exc_info:
        await service.export_async(
            cycle_id=cycle.id,
            scope=scope,
            export_format="csv",
            user=user,
        )
    assert exc_info.value.code == "REPORT_002"


@pytest.mark.asyncio
async def test_report_export_handler_run(
    fake_report: ConsolidatedReport,
    tmp_storage: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end handler.run() produces a file + calls the notification factory."""
    from app.domain.consolidation import export as export_module

    sent_notifications: list[dict[str, Any]] = []

    class _FakeNotifications:
        async def send(self, **kwargs: Any) -> Any:
            sent_notifications.append(kwargs)
            return object()

    user_id = uuid4()
    cycle_id = fake_report.cycle_id
    user_row = make_user()
    user_row.id = user_id

    cycle_row = make_cycle(state=CycleState.open)
    cycle_row.id = cycle_id

    class _SessionCM:
        """Session context manager emulating ``async with`` usage."""

        def __init__(self, session: Any) -> None:
            self._session = session

        async def __aenter__(self) -> Any:
            return self._session

        async def __aexit__(self, *args: Any) -> None:
            return None

    class _SessionFactory:
        def __call__(self) -> _SessionCM:
            session = StubSession()
            session.register_cycle(cycle_row)
            session.register_user(user_row)
            return _SessionCM(session)

    # Patch the session-creating report service to return our fake.
    real_service = export_module.ConsolidatedReportService

    class _StubRS:
        def __init__(self, _db: Any) -> None:
            pass

        async def build(self, *, cycle_id: Any, scope: Any) -> ConsolidatedReport:
            return fake_report

    monkeypatch.setattr(export_module, "ConsolidatedReportService", _StubRS)

    class _StubAudit:
        def __init__(self, _db: Any) -> None:
            self.events: list[dict[str, Any]] = []

        async def record(self, **kwargs: Any) -> None:
            self.events.append(kwargs)

    monkeypatch.setattr(export_module, "AuditService", _StubAudit)

    handler = export_module.ReportExportHandler(
        session_factory=_SessionFactory(),  # type: ignore[arg-type]
        notification_factory=lambda _session: _FakeNotifications(),
    )

    result = await handler.run(
        {
            "cycle_id": str(cycle_id),
            "scope_all": False,
            "scope_org_unit_ids": [],
            "format": "csv",
            "user_id": str(user_id),
        }
    )

    assert "file_url" in result
    assert result["row_count"] == 0
    assert len(sent_notifications) == 1

    # Restore original for other tests.
    monkeypatch.setattr(export_module, "ConsolidatedReportService", real_service)
