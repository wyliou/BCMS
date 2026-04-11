"""Shared fixtures for api-tier tests.

Batch 2 wired a real ``require_role`` dependency that resolves the
current user from a ``bc_session`` cookie. The api tests written in
Batches 1 and 2 use dependency_overrides for the *service* layer but
do not issue real SSO callbacks, so every request would otherwise
return ``AUTH_002``. This autouse fixture short-circuits the SSO lookup
by patching :meth:`app.core.security.auth_service.AuthService.current_user`
to return a globally-scoped SystemAdmin user for the duration of each
api test. Tests that need to exercise the unauthenticated path can
monkey-patch ``AuthService.current_user`` themselves.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.security.auth_service import AuthService
from app.core.security.models import User
from app.core.security.roles import Role
from app.domain.audit.models import AuditLog
from app.domain.audit.service import AuditService


@pytest.fixture(autouse=True)
def _auto_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace :meth:`AuditService.record` with a no-op for api tests.

    api-tier tests drive routes against fake sessions that do not
    implement the SQLAlchemy ``execute``/``add``/``refresh`` surface the
    real :class:`AuditService` relies on. Short-circuiting ``record`` at
    the class level keeps the CR-006 (audit AFTER commit) sequencing
    semantics verified by the unit tier while letting api tests exercise
    route wiring.
    """

    async def _noop_record(self: AuditService, **kwargs: object) -> AuditLog:
        return AuditLog()  # type: ignore[call-arg]

    monkeypatch.setattr(AuditService, "record", _noop_record)


@pytest.fixture(autouse=True)
def _auto_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``AuthService.current_user`` with a SystemAdmin fake.

    The SystemAdmin role is global so every ``scoped_org_units`` check
    returns :data:`app.core.security.rbac.ALL_SCOPES`. Tests that want
    to verify 401/403 behavior override this fixture locally.
    """
    fake_user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Test Admin",
        email_enc=b"",
        email_hash=b"\x00" * 32,
        roles=[Role.SystemAdmin.value, Role.ITSecurityAuditor.value, Role.FinanceAdmin.value],
        org_unit_id=None,
        is_active=True,
    )

    async def _fake_current_user(self: AuthService, request: object) -> User:
        return fake_user

    monkeypatch.setattr(AuthService, "current_user", _fake_current_user)
