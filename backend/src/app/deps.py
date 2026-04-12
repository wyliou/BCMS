"""FastAPI dependency-injection factories.

Thin re-exports + service factories used by the route handlers. Every
factory is an ``async def`` that accepts a :class:`AsyncSession` (via
:func:`app.infra.db.session.get_session`) and returns a fresh,
request-scoped service. No business logic lives here — the service
classes own that.

The functions ``get_session`` and :func:`get_current_user` are the
canonical names used by :mod:`app.api.v1.orchestrators.open_cycle`
and the router unit tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthenticatedError
from app.core.security.auth_service import AuthService
from app.core.security.models import User
from app.domain.accounts.service import AccountService
from app.domain.audit.service import AuditService
from app.domain.budget_uploads.service import BudgetUploadService
from app.domain.consolidation.dashboard import DashboardService
from app.domain.consolidation.export import ReportExportService
from app.domain.consolidation.report import ConsolidatedReportService
from app.domain.cycles.service import CycleService
from app.domain.notifications.service import NotificationService
from app.domain.personnel.service import PersonnelImportService
from app.domain.shared_costs.service import SharedCostImportService
from app.domain.templates.service import TemplateService
from app.infra.db.session import get_session as _infra_get_session

__all__ = [
    "get_account_service",
    "get_audit_service",
    "get_budget_upload_service",
    "get_current_user",
    "get_cycle_service",
    "get_dashboard_service",
    "get_export_service",
    "get_notification_service",
    "get_personnel_service",
    "get_report_service",
    "get_session",
    "get_shared_cost_service",
    "get_template_service",
]


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a per-request :class:`AsyncSession`.

    Re-exported from :mod:`app.infra.db.session` so route handlers can
    import session from the single ``app.deps`` namespace.

    Yields:
        AsyncSession: Active database session.
    """
    async for session in _infra_get_session():
        yield session


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the authenticated user from the ``bc_session`` cookie.

    Thin wrapper over :meth:`AuthService.current_user` so FastAPI
    ``Depends`` can inject both the request and the session.

    Args:
        request: FastAPI request.
        db: Injected async session.

    Returns:
        User: Authenticated caller.

    Raises:
        UnauthenticatedError: ``AUTH_002`` on missing/expired cookies.
    """
    service = AuthService(db)
    return await service.current_user(request)


async def get_audit_service(
    db: AsyncSession = Depends(get_session),
) -> AuditService:
    """Factory for :class:`AuditService`.

    Args:
        db: Injected async session.

    Returns:
        AuditService: Fresh service instance.
    """
    return AuditService(db)


async def get_cycle_service(
    db: AsyncSession = Depends(get_session),
) -> CycleService:
    """Factory for :class:`CycleService`.

    Args:
        db: Injected async session.

    Returns:
        CycleService: Fresh service instance.
    """
    return CycleService(db)


async def get_account_service(
    db: AsyncSession = Depends(get_session),
) -> AccountService:
    """Factory for :class:`AccountService`.

    Args:
        db: Injected async session.

    Returns:
        AccountService: Fresh service instance.
    """
    return AccountService(db)


async def get_template_service(
    db: AsyncSession = Depends(get_session),
) -> TemplateService:
    """Factory for :class:`TemplateService`.

    Args:
        db: Injected async session.

    Returns:
        TemplateService: Fresh service instance.
    """
    return TemplateService(db)


async def get_budget_upload_service(
    db: AsyncSession = Depends(get_session),
) -> BudgetUploadService:
    """Factory for :class:`BudgetUploadService`.

    Args:
        db: Injected async session.

    Returns:
        BudgetUploadService: Fresh service instance.
    """
    return BudgetUploadService(db)


async def get_personnel_service(
    db: AsyncSession = Depends(get_session),
) -> PersonnelImportService:
    """Factory for :class:`PersonnelImportService`.

    Args:
        db: Injected async session.

    Returns:
        PersonnelImportService: Fresh service instance.
    """
    return PersonnelImportService(db)


async def get_shared_cost_service(
    db: AsyncSession = Depends(get_session),
) -> SharedCostImportService:
    """Factory for :class:`SharedCostImportService`.

    Args:
        db: Injected async session.

    Returns:
        SharedCostImportService: Fresh service instance.
    """
    return SharedCostImportService(db)


async def get_notification_service(
    db: AsyncSession = Depends(get_session),
) -> NotificationService | None:
    """Factory for :class:`NotificationService`.

    The production :class:`NotificationService` requires an
    :class:`~app.infra.email.EmailClient`. Wiring a real client
    depends on per-deployment SMTP config — this dependency returns
    ``None`` when no client is available so callers fall through to
    the best-effort CR-029 path (silent skip). Tests override this
    factory with a fake that implements :class:`EmailSender`.

    Args:
        db: Injected async session.

    Returns:
        NotificationService | None: Fresh service or ``None`` when no
        email client is wired.
    """
    del db
    return None


async def get_dashboard_service(
    db: AsyncSession = Depends(get_session),
) -> DashboardService:
    """Factory for :class:`DashboardService`.

    Args:
        db: Injected async session.

    Returns:
        DashboardService: Fresh service instance.
    """
    return DashboardService(db)


async def get_report_service(
    db: AsyncSession = Depends(get_session),
) -> ConsolidatedReportService:
    """Factory for :class:`ConsolidatedReportService`.

    Args:
        db: Injected async session.

    Returns:
        ConsolidatedReportService: Fresh service instance.
    """
    return ConsolidatedReportService(db)


async def get_export_service(
    db: AsyncSession = Depends(get_session),
) -> ReportExportService:
    """Factory for :class:`ReportExportService`.

    Args:
        db: Injected async session.

    Returns:
        ReportExportService: Fresh service instance.
    """
    return ReportExportService(db)


async def _raise_unauthenticated() -> None:
    """Raise a generic :class:`UnauthenticatedError` — unused placeholder."""
    raise UnauthenticatedError("AUTH_002", "unauthenticated")
