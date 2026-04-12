"""Pydantic models for the consolidated report (FR-015, FR-016).

Extracted from :mod:`app.domain.consolidation.report` to keep each
source file under the 500-line hard limit.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ConsolidatedReport",
    "ConsolidatedReportRow",
    "ExportFormat",
    "ReportScope",
]


class ExportFormat(BaseModel):
    """Typed enum wrapper for the export format selection.

    Attributes:
        value: Wire value — ``"xlsx"`` or ``"csv"``.
    """

    model_config = ConfigDict(frozen=True)

    value: Literal["xlsx", "csv"] = "xlsx"


class ReportScope(BaseModel):
    """RBAC-resolved scope for a report build call.

    Attributes:
        user_id: UUID of the requesting user (audit + notifications).
        org_unit_ids: Explicit set of permitted org unit UUIDs. An empty
            set means "no scope" (service returns an empty report).
        all_scopes: Sentinel — when ``True``, ``org_unit_ids`` is
            ignored and every org unit is considered in scope.
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    org_unit_ids: frozenset[UUID] = frozenset()
    all_scopes: bool = False


class ConsolidatedReportRow(BaseModel):
    """One row of the consolidated report.

    Attributes:
        org_unit_id: Filing unit UUID.
        org_unit_name: Filing unit display name.
        account_code: Account code string.
        account_name: Account code display name.
        actual: Actual amount, ``None`` when no row exists.
        operational_budget: Latest-version operational budget amount,
            ``None`` when no upload exists (CR-015).
        personnel_budget: Personnel budget amount, ``None`` below
            level 1000 (CR-016).
        shared_cost: Shared cost amount, ``None`` below level 1000.
        delta_amount: ``operational_budget - actual`` when both known.
        delta_pct: One-decimal percent or ``"N/A"`` (CR-013, CR-014).
        budget_status: ``"uploaded"`` or ``"not_uploaded"`` (CR-015).
    """

    model_config = ConfigDict(json_encoders={Decimal: str})

    org_unit_id: UUID
    org_unit_name: str
    account_code: str
    account_name: str
    actual: Decimal | None = None
    operational_budget: Decimal | None = None
    personnel_budget: Decimal | None = None
    shared_cost: Decimal | None = None
    delta_amount: Decimal | None = None
    delta_pct: str = "N/A"
    budget_status: Literal["uploaded", "not_uploaded"] = "not_uploaded"


class ConsolidatedReport(BaseModel):
    """Top-level consolidated report response.

    Attributes:
        cycle_id: UUID of the source cycle.
        rows: Flat list of report rows.
        reporting_currency: Echoed from cycle (CR-036).
        budget_last_updated_at: Latest budget upload timestamp.
        personnel_last_updated_at: Latest personnel upload timestamp.
        shared_cost_last_updated_at: Latest shared cost upload timestamp.
    """

    model_config = ConfigDict(json_encoders={Decimal: str})

    cycle_id: UUID
    rows: list[ConsolidatedReportRow] = []
    reporting_currency: str = "TWD"
    budget_last_updated_at: datetime | None = None
    personnel_last_updated_at: datetime | None = None
    shared_cost_last_updated_at: datetime | None = None
