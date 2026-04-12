"""Top-level ``/api/v1`` router aggregator.

Imports every sub-router and mounts them on a single
:class:`fastapi.APIRouter`. The aggregator is the only place that knows
the full v1 surface area — :mod:`app.main` includes this router as the
sole ``/api/v1`` mount.

No business logic lives here; the file is 100% imports + ``include_router``
calls.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.accounts import cycles_router as accounts_cycles_router
from app.api.v1.accounts import router as accounts_router
from app.api.v1.admin.org_units import router as admin_org_units_router
from app.api.v1.admin.users import router as admin_users_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.budget_uploads import router as budget_uploads_router
from app.api.v1.cycles import router as cycles_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.notifications import resubmit_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.orchestrators.open_cycle import router as open_cycle_router
from app.api.v1.personnel import router as personnel_router
from app.api.v1.reports import router as reports_router
from app.api.v1.shared_costs import router as shared_costs_router
from app.api.v1.templates import router as templates_router

__all__ = ["router"]


router = APIRouter()

router.include_router(auth_router)
router.include_router(cycles_router)
router.include_router(open_cycle_router)
router.include_router(templates_router)
router.include_router(accounts_router)
router.include_router(accounts_cycles_router)
router.include_router(budget_uploads_router)
router.include_router(personnel_router)
router.include_router(shared_costs_router)
router.include_router(dashboard_router)
router.include_router(reports_router)
router.include_router(notifications_router)
router.include_router(resubmit_router)
router.include_router(audit_router)
router.include_router(admin_org_units_router)
router.include_router(admin_users_router)
