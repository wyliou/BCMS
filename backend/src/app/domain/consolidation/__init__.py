"""Consolidation domain — dashboard, consolidated report, and export.

M7 is split into three modules per spec §4:

* :mod:`app.domain.consolidation.dashboard` — per-role dashboard
  (FR-004, FR-014).
* :mod:`app.domain.consolidation.report` — three-source consolidated
  report builder (FR-015, FR-016).
* :mod:`app.domain.consolidation.export` — sync / async export
  dispatch + durable job handler (FR-017).
"""

from __future__ import annotations

from app.domain.consolidation.dashboard import (
    DashboardFilters,
    DashboardItem,
    DashboardResponse,
    DashboardService,
    DashboardStatus,
)
from app.domain.consolidation.export import (
    ExportEnqueueResult,
    ReportExportHandler,
    ReportExportService,
    register_report_export_handler,
)
from app.domain.consolidation.report import (
    ConsolidatedReport,
    ConsolidatedReportRow,
    ConsolidatedReportService,
    ExportFormat,
    ReportScope,
)

__all__ = [
    "ConsolidatedReport",
    "ConsolidatedReportRow",
    "ConsolidatedReportService",
    "DashboardFilters",
    "DashboardItem",
    "DashboardResponse",
    "DashboardService",
    "DashboardStatus",
    "ExportEnqueueResult",
    "ExportFormat",
    "ReportExportHandler",
    "ReportExportService",
    "ReportScope",
    "register_report_export_handler",
]
