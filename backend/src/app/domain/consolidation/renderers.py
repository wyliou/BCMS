"""Report rendering helpers for consolidated report export.

Extracted from :mod:`app.domain.consolidation.export` to keep each
source file under the 500-line hard limit.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Literal
from uuid import UUID

from app.domain.consolidation.report_models import (
    ConsolidatedReport,
    ConsolidatedReportRow,
)
from app.infra.excel import workbook_to_bytes, write_workbook

__all__ = [
    "render_report",
]


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


def render_report(
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
