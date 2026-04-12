"""Unit tests for the open-cycle orchestrator (FR-003)."""

from __future__ import annotations

from typing import Any

import pytest

from app.api.v1.orchestrators.open_cycle import open_cycle
from app.core.errors import AppError, ConflictError, ForbiddenError
from app.core.security.roles import Role
from app.domain.templates.service import TemplateGenerationResult
from tests.unit.consolidation.conftest import (
    StubSession,
    make_cycle,
    make_org_unit,
    make_user,
)


class FakeCycleService:
    """Recording stub for :class:`CycleService`."""

    def __init__(self, *, cycle: Any, units: list[Any]) -> None:
        """Initialize with the pre-baked return value."""
        self._cycle = cycle
        self._units = units
        self.open_calls: list[Any] = []
        self.fail_with: Exception | None = None

    async def open(self, cycle_id: Any, user: Any) -> tuple[Any, list[Any]]:
        """Record the call and return the fixed cycle + units."""
        self.open_calls.append({"cycle_id": cycle_id, "user": user})
        if self.fail_with is not None:
            raise self.fail_with
        return self._cycle, self._units


class FakeTemplateService:
    """Recording stub for :class:`TemplateService`."""

    def __init__(self, *, results: list[TemplateGenerationResult]) -> None:
        """Initialize with the pre-baked per-unit results."""
        self._results = results
        self.calls: list[Any] = []

    async def generate_for_cycle(
        self,
        *,
        cycle: Any,
        filing_units: list[Any],
        user: Any,
    ) -> list[TemplateGenerationResult]:
        """Record and return the fixed result list."""
        self.calls.append({"cycle": cycle, "filing_units": filing_units, "user": user})
        return list(self._results)


class FakeNotificationService:
    """Recording stub for :class:`NotificationService`."""

    def __init__(self, *, fail: bool = False) -> None:
        """Initialize the capture + failure flag."""
        self.batches: list[dict[str, Any]] = []
        self.fail = fail

    async def send_batch(
        self,
        *,
        template: Any,
        recipients: list[tuple[Any, str]],
        context: dict[str, Any],
        related: tuple[str, Any] | None = None,
    ) -> list[Any]:
        """Capture the call and return one success row per recipient."""
        if self.fail:
            raise AppError("NOTIFY_001", "smtp boom")
        self.batches.append(
            {
                "template": template,
                "recipients": list(recipients),
                "context": dict(context),
                "related": related,
            }
        )
        return [type("N", (), {"status": "sent"})() for _ in recipients]


class _ScriptedSession(StubSession):
    """StubSession that returns a scripted users list from :meth:`execute`."""

    def __init__(self, users: list[Any]) -> None:
        """Initialize and stash the users."""
        super().__init__()
        self._users_list = users

    async def execute(self, _stmt: Any) -> Any:
        """Return the stored users as an iterable :class:`_Result`."""

        class _Res:
            def __init__(self, rows: list[Any]) -> None:
                self._rows = rows

            def scalars(self) -> Any:
                return self

            def all(self) -> list[Any]:
                return list(self._rows)

            def first(self) -> Any:
                return self._rows[0] if self._rows else None

        return _Res(self._users_list)


@pytest.mark.asyncio
async def test_happy_path_invokes_all_steps_in_order() -> None:
    """3 filing units all succeed → templates generated + notifications sent."""
    cycle = make_cycle()
    unit_a = make_org_unit(code="4001")
    unit_b = make_org_unit(code="4002")
    unit_c = make_org_unit(code="4003")
    user_a = make_user(role=Role.FilingUnitManager, org_unit_id=unit_a.id)
    user_b = make_user(role=Role.FilingUnitManager, org_unit_id=unit_b.id)
    user_c = make_user(role=Role.FilingUnitManager, org_unit_id=unit_c.id)

    session = _ScriptedSession([user_a, user_b, user_c])

    cycle_svc = FakeCycleService(cycle=cycle, units=[unit_a, unit_b, unit_c])
    tpl_svc = FakeTemplateService(
        results=[
            TemplateGenerationResult(org_unit_id=unit_a.id, status="generated"),
            TemplateGenerationResult(org_unit_id=unit_b.id, status="generated"),
            TemplateGenerationResult(org_unit_id=unit_c.id, status="generated"),
        ]
    )
    notif_svc = FakeNotificationService()

    caller = make_user(role=Role.FinanceAdmin)
    response = await open_cycle(
        session=session,  # type: ignore[arg-type]
        cycle_id=cycle.id,
        user=caller,
        cycle_service=cycle_svc,  # type: ignore[arg-type]
        template_service=tpl_svc,  # type: ignore[arg-type]
        notification_service=notif_svc,  # type: ignore[arg-type]
    )

    assert response.generation_summary.generated == 3
    assert response.generation_summary.errors == 0
    assert response.dispatch_summary.total_recipients == 3
    assert response.dispatch_summary.sent == 3
    assert len(cycle_svc.open_calls) == 1
    assert len(tpl_svc.calls) == 1
    assert len(notif_svc.batches) == 1


@pytest.mark.asyncio
async def test_per_unit_generation_error_skips_notification() -> None:
    """Failed-generation units are excluded from notifications."""
    cycle = make_cycle()
    unit_a = make_org_unit(code="4001")
    unit_b = make_org_unit(code="4002")
    unit_c = make_org_unit(code="4003")
    user_a = make_user(role=Role.FilingUnitManager, org_unit_id=unit_a.id)
    user_c = make_user(role=Role.FilingUnitManager, org_unit_id=unit_c.id)

    session = _ScriptedSession([user_a, user_c])

    cycle_svc = FakeCycleService(cycle=cycle, units=[unit_a, unit_b, unit_c])
    tpl_svc = FakeTemplateService(
        results=[
            TemplateGenerationResult(org_unit_id=unit_a.id, status="generated"),
            TemplateGenerationResult(org_unit_id=unit_b.id, status="error", error="storage down"),
            TemplateGenerationResult(org_unit_id=unit_c.id, status="generated"),
        ]
    )
    notif_svc = FakeNotificationService()

    caller = make_user(role=Role.FinanceAdmin)
    response = await open_cycle(
        session=session,  # type: ignore[arg-type]
        cycle_id=cycle.id,
        user=caller,
        cycle_service=cycle_svc,  # type: ignore[arg-type]
        template_service=tpl_svc,  # type: ignore[arg-type]
        notification_service=notif_svc,  # type: ignore[arg-type]
    )

    assert response.generation_summary.generated == 2
    assert response.generation_summary.errors == 1
    assert len(response.generation_summary.error_details) == 1
    # Only 2 recipients — unit_b user not in the scripted list.
    assert response.dispatch_summary.total_recipients == 2
    assert response.dispatch_summary.sent == 2


@pytest.mark.asyncio
async def test_cycle_open_cycle_002_propagates() -> None:
    """A ``CYCLE_002`` from Step 2 propagates unchanged; Steps 3-4 do not run."""
    cycle = make_cycle()
    session = _ScriptedSession([])

    cycle_svc = FakeCycleService(cycle=cycle, units=[])
    cycle_svc.fail_with = ConflictError("CYCLE_002", "missing manager")
    tpl_svc = FakeTemplateService(results=[])
    notif_svc = FakeNotificationService()

    caller = make_user(role=Role.FinanceAdmin)
    with pytest.raises(ConflictError) as exc_info:
        await open_cycle(
            session=session,  # type: ignore[arg-type]
            cycle_id=cycle.id,
            user=caller,
            cycle_service=cycle_svc,  # type: ignore[arg-type]
            template_service=tpl_svc,  # type: ignore[arg-type]
            notification_service=notif_svc,  # type: ignore[arg-type]
        )
    assert exc_info.value.code == "CYCLE_002"
    assert tpl_svc.calls == []
    assert notif_svc.batches == []


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_endpoint() -> None:
    """SMTP failure is surfaced in dispatch_summary, not as an HTTP error."""
    cycle = make_cycle()
    unit = make_org_unit(code="4001")
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)
    session = _ScriptedSession([user])

    cycle_svc = FakeCycleService(cycle=cycle, units=[unit])
    tpl_svc = FakeTemplateService(
        results=[TemplateGenerationResult(org_unit_id=unit.id, status="generated")]
    )
    notif_svc = FakeNotificationService(fail=True)

    caller = make_user(role=Role.FinanceAdmin)
    response = await open_cycle(
        session=session,  # type: ignore[arg-type]
        cycle_id=cycle.id,
        user=caller,
        cycle_service=cycle_svc,  # type: ignore[arg-type]
        template_service=tpl_svc,  # type: ignore[arg-type]
        notification_service=notif_svc,  # type: ignore[arg-type]
    )

    assert response.dispatch_summary.errors == 1
    assert response.dispatch_summary.sent == 0


@pytest.mark.asyncio
async def test_rbac_defence_in_depth() -> None:
    """A caller without the required role is rejected by the orchestrator body."""
    cycle = make_cycle()
    session = _ScriptedSession([])
    cycle_svc = FakeCycleService(cycle=cycle, units=[])
    tpl_svc = FakeTemplateService(results=[])
    notif_svc = FakeNotificationService()

    caller = make_user(role=Role.FilingUnitManager)
    with pytest.raises(ForbiddenError) as exc_info:
        await open_cycle(
            session=session,  # type: ignore[arg-type]
            cycle_id=cycle.id,
            user=caller,
            cycle_service=cycle_svc,  # type: ignore[arg-type]
            template_service=tpl_svc,  # type: ignore[arg-type]
            notification_service=notif_svc,  # type: ignore[arg-type]
        )
    assert exc_info.value.code == "RBAC_001"
