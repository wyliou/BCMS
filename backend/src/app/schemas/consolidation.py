"""Pydantic schemas for the consolidation endpoints (M7).

These are thin re-exports of the Pydantic models defined inside
:mod:`app.domain.consolidation` so the FastAPI route signatures and
OpenAPI schema generation can reference a single
``app.schemas.consolidation`` namespace.
"""

from __future__ import annotations

from app.domain.consolidation.dashboard import (
    DashboardFilters,
    DashboardItem,
    DashboardResponse,
    DashboardStatus,
)
from app.domain.consolidation.export import ExportEnqueueResult
from app.domain.consolidation.report import (
    ConsolidatedReport,
    ConsolidatedReportRow,
    ExportFormat,
    ReportScope,
)

__all__ = [
    "ConsolidatedReport",
    "ConsolidatedReportRow",
    "DashboardFilters",
    "DashboardItem",
    "DashboardResponse",
    "DashboardStatus",
    "ExportEnqueueResult",
    "ExportFormat",
    "ReportScope",
]
