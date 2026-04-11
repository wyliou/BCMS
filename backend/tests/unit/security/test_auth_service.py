"""Unit tests for :class:`app.core.security.auth_service.AuthService`.

These tests use the real :class:`AuthService` against an in-memory
FakeDB (session-like) and a shared :class:`app.infra.sso.FakeSSO`
double for IdP round-trips. Audit side-session calls are redirected to
a throwaway :class:`_RecordingAuditSession` so tests can assert that
``LOGIN_SUCCESS``/``AUTH_FAILED`` rows are written on the correct
audit codes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.errors import InfraError, UnauthenticatedError
from app.core.security import auth_service as auth_service_module
from app.core.security.auth_service import AuthService
from app.core.security.models import User
from app.domain.audit.actions import AuditAction
from app.infra.sso import FakeSSO


# --------------------------------------------------------------------------- fake DB
class _FakeDB:
    """Minimal in-memory AsyncSession double for the primary session."""

    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.sessions: dict[UUID, Any] = {}
        self.committed = False

    def add(self, row: Any) -> None:
        from app.core.security.models import Session as SessionRow

        if isinstance(row, User):
            if row.id is None:
                row.id = uuid4()
            self.users[row.id] = row
        elif isinstance(row, SessionRow):
            if row.id is None:
                row.id = uuid4()
            self.sessions[row.id] = row

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def get(self, model: type, pk: UUID) -> Any:
        from app.core.security.models import Session as SessionRow

        if model is User:
            return self.users.get(pk)
        if model is SessionRow:
            return self.sessions.get(pk)
        return None

    async def execute(self, stmt: Any) -> Any:
        """Support the two lookups AuthService needs.

        * ``select(User).where(User.sso_id_hash == digest)``
        * ``select(Session).where(Session.refresh_token_hash == digest)``
        """
        compiled = stmt.compile()
        params = compiled.params
        target_bytes: bytes | None = None
        for value in params.values():
            if isinstance(value, (bytes, bytearray)):
                target_bytes = bytes(value)
                break

        users = [u for u in self.users.values() if u.sso_id_hash == target_bytes]

        class _Scalars:
            def __init__(self, rows: list[Any]) -> None:
                self._rows = rows

            def first(self) -> Any:
                return self._rows[0] if self._rows else None

            def all(self) -> list[Any]:
                return list(self._rows)

        class _Result:
            def __init__(self, rows: list[Any]) -> None:
                self._rows = rows

            def scalars(self) -> _Scalars:
                return _Scalars(self._rows)

        return _Result(users)


# --------------------------------------------------------------------------- audit spy
@pytest.fixture
def audit_records(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture every audit call made by ``AuthService._record_audit_side_session``.

    Patches the helper to skip the real DB write and append an
    invocation record instead.
    """
    captured: list[dict[str, Any]] = []

    async def _fake_record(**kwargs: Any) -> None:
        captured.append(kwargs)

    monkeypatch.setattr(
        AuthService,
        "_record_audit_side_session",
        staticmethod(_fake_record),
    )
    return captured


# --------------------------------------------------------------------------- role mapping
@pytest.fixture
def _seed_role_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seed ``BC_SSO_ROLE_MAPPING`` with a predictable group → role mapping."""
    monkeypatch.setenv("BC_SSO_ROLE_MAPPING", '{"BC_FINANCE":"FinanceAdmin"}')
    from app.config import get_settings

    get_settings.cache_clear()


# --------------------------------------------------------------------------- tests
async def test_handle_sso_callback_success(
    audit_records: list[dict[str, Any]],
    _seed_role_mapping: None,
) -> None:
    """Happy path — LOGIN_SUCCESS audited after commit."""
    db = _FakeDB()
    sso = FakeSSO(
        userinfo={
            "sub": "u-1",
            "email": "finance@example.invalid",
            "name": "Finance Lead",
            "groups": ["BC_FINANCE"],
        }
    )
    service = AuthService(db, sso_client=sso)  # type: ignore[arg-type]

    tokens = await service.handle_sso_callback(
        provider="oidc",
        payload={"code": "abc"},
        ip="127.0.0.1",
        user_agent="pytest",
    )

    assert tokens.access_token and tokens.refresh_token and tokens.csrf_token
    assert db.committed is True
    assert len(db.users) == 1
    actions = [r["action"] for r in audit_records]
    assert AuditAction.LOGIN_SUCCESS in actions


async def test_handle_sso_callback_idp_down_raises_auth_001(
    audit_records: list[dict[str, Any]],
    _seed_role_mapping: None,
) -> None:
    """IdP failure raises AUTH_001 and writes no user row."""
    db = _FakeDB()
    sso = FakeSSO(should_fail_auth_001=True)
    service = AuthService(db, sso_client=sso)  # type: ignore[arg-type]

    with pytest.raises(InfraError) as excinfo:
        await service.handle_sso_callback(
            provider="oidc",
            payload={"code": "abc"},
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.code == "AUTH_001"
    assert db.users == {}
    assert db.committed is False


async def test_handle_sso_callback_no_role_mapping_raises_auth_003(
    audit_records: list[dict[str, Any]],
    _seed_role_mapping: None,
) -> None:
    """Group not in mapping raises AUTH_003 and audits AUTH_FAILED."""
    db = _FakeDB()
    sso = FakeSSO(
        userinfo={
            "sub": "u-2",
            "email": "random@example.invalid",
            "name": "Random",
            "groups": ["BC_UNKNOWN"],
        }
    )
    service = AuthService(db, sso_client=sso)  # type: ignore[arg-type]

    with pytest.raises(UnauthenticatedError) as excinfo:
        await service.handle_sso_callback(
            provider="oidc",
            payload={"code": "abc"},
            ip=None,
            user_agent=None,
        )
    assert excinfo.value.code == "AUTH_003"
    assert db.users == {}

    # AUTH_FAILED audit must have been recorded.
    actions = [r["action"] for r in audit_records]
    assert AuditAction.AUTH_FAILED in actions
    failed = next(r for r in audit_records if r["action"] == AuditAction.AUTH_FAILED)
    assert failed["user_id"] is None


async def test_handle_sso_callback_requires_code(
    audit_records: list[dict[str, Any]],
    _seed_role_mapping: None,
) -> None:
    """Missing 'code' in payload raises AUTH_001."""
    db = _FakeDB()
    service = AuthService(db, sso_client=FakeSSO())  # type: ignore[arg-type]
    with pytest.raises(InfraError) as excinfo:
        await service.handle_sso_callback(provider="oidc", payload={}, ip=None, user_agent=None)
    assert excinfo.value.code == "AUTH_001"


def test_auth_service_module_exports_cookie_names() -> None:
    """Cookie-name constants are importable from the auth service module."""
    assert auth_service_module.SESSION_COOKIE_NAME == "bc_session"
    assert auth_service_module.REFRESH_COOKIE_NAME == "bc_refresh"
