"""Public re-exports for :mod:`app.domain.cycles`.

Downstream batches (M4/M5 importers and the Batch 6 orchestrator)
import :class:`CycleService` from this package. The import shape is
flat so the Batch 3 lazy ``importlib.import_module('app.domain.cycles
.service')`` call site keeps working.
"""

from __future__ import annotations

from app.domain.cycles.filing_units import FilingUnitInfo, list_filing_units
from app.domain.cycles.models import (
    BudgetCycle,
    CycleReminderSchedule,
    CycleState,
    OrgUnit,
)
from app.domain.cycles.reminders import (
    DispatchSummary,
    dispatch_deadline_reminders,
    register_cron_callback,
    set_reminder_schedule,
)
from app.domain.cycles.service import CycleService
from app.domain.cycles.state_machine import assert_transition, can_transition

__all__ = [
    "BudgetCycle",
    "CycleReminderSchedule",
    "CycleService",
    "CycleState",
    "DispatchSummary",
    "FilingUnitInfo",
    "OrgUnit",
    "assert_transition",
    "can_transition",
    "dispatch_deadline_reminders",
    "list_filing_units",
    "register_cron_callback",
    "set_reminder_schedule",
]
