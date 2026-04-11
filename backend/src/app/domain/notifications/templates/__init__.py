"""Single-source-of-truth :class:`NotificationTemplate` enum (CR-003 owner).

This package owns **CR-003**: every call to
:meth:`NotificationService.send` / :meth:`NotificationService.send_batch`
across the backend must pass a member of :class:`NotificationTemplate` —
no bare string literals.

The enum values exactly match the ``*.txt`` filenames shipped alongside
this ``__init__.py`` (each file is a Jinja2 template with a subject header
as its first non-comment line). A final-gate check cross-references both
sources so any drift fails CI.

The members also mirror the Postgres ``notification_type`` enum declared in
the Alembic baseline — adding a new template requires a DB migration as
well as an enum member here and a template file.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

__all__ = ["NotificationTemplate", "TEMPLATES_DIR"]


# Reason: compute relative to this file so the packaged wheel and editable
# install both resolve the same directory, and tests can point jinja2 at an
# alternative path by passing ``template_dir`` to :class:`EmailClient`.
TEMPLATES_DIR: Path = Path(__file__).resolve().parent


class NotificationTemplate(StrEnum):
    """Canonical enum of every notification template name in BCMS.

    Values must match filenames (without ``.txt``) under
    :data:`TEMPLATES_DIR`. This enum is the ONLY place where template
    names may be defined — callers in ``domain/cycles``,
    ``domain/budget_uploads``, ``domain/personnel`` and
    ``domain/shared_costs`` must import from here (CR-003).
    """

    CYCLE_OPENED = "cycle_opened"
    UPLOAD_CONFIRMED = "upload_confirmed"
    RESUBMIT_REQUESTED = "resubmit_requested"
    DEADLINE_REMINDER = "deadline_reminder"
    PERSONNEL_IMPORTED = "personnel_imported"
    SHARED_COST_IMPORTED = "shared_cost_imported"
