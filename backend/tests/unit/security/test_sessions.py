"""Unit tests for :mod:`app.core.security.sessions`.

The fake DB layer in this module is deliberately minimal — it owns
neither SQLAlchemy nor aiosqlite — and exercises the real
:class:`SessionStore` against an in-memory row store. Integration-level
round-trip testing happens in
``tests/integration/security/test_sessions.py`` against real Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.errors import UnauthenticatedError
from app.core.security.models import Session, User
from app.core.security.roles import Role
from app.core.security.sessions import SessionStore
from app.infra.crypto import hmac_lookup_hash


def _make_user() -> User:
    """Return a minimal :class:`User` suitable for unit tests."""
    return User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Test User",
        email_enc=b"",
        email_hash=b"\x01" * 32,
        roles=[Role.FilingUnitManager.value],
        org_unit_id=uuid4(),
        is_active=True,
    )


class _FakeDB:
    """In-memory stand-in for :class:`AsyncSession` used by session tests."""

    def __init__(self, seeded_user: User) -> None:
        """Seed the store with a single user row."""
        self.sessions: dict[UUID, Session] = {}
        self.users: dict[UUID, User] = {seeded_user.id: seeded_user}
        self.committed = False

    def add(self, row: Any) -> None:
        """Append a session row with a fresh id."""
        if isinstance(row, Session):
            if row.id is None:
                row.id = uuid4()
            self.sessions[row.id] = row

    async def flush(self) -> None:
        """Async no-op."""
        return None

    async def commit(self) -> None:
        """Record that commit was called."""
        self.committed = True

    async def get(self, model: type, pk: UUID) -> Any:
        """Return the stored row by primary key."""
        if model is Session:
            return self.sessions.get(pk)
        if model is User:
            return self.users.get(pk)
        return None

    async def execute(self, stmt: Any) -> Any:
        """Minimal shim for the refresh lookup by ``refresh_token_hash``.

        The :class:`SessionStore.refresh` method executes
        ``select(Session).where(Session.refresh_token_hash == digest)`` —
        we inspect the compiled statement's bound parameters, match
        rows in-memory, and return a lightweight result shape that
        exposes ``.scalars().first()``.
        """
        compiled = stmt.compile()
        params = compiled.params
        target_hash: bytes | None = None
        for value in params.values():
            if isinstance(value, (bytes, bytearray)):
                target_hash = bytes(value)
                break

        matches: list[Session] = []
        if target_hash is not None:
            for row in self.sessions.values():
                if row.refresh_token_hash == target_hash:
                    matches.append(row)

        class _Scalars:
            def __init__(self, rows: list[Session]) -> None:
                self._rows = rows

            def first(self) -> Session | None:
                return self._rows[0] if self._rows else None

            def all(self) -> list[Session]:
                return list(self._rows)

        class _Result:
            def __init__(self, rows: list[Session]) -> None:
                self._rows = rows

            def scalars(self) -> _Scalars:
                return _Scalars(self._rows)

        return _Result(matches)


@pytest.fixture(autouse=True)
def _pin_refresh_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force a known refresh TTL so absolute_expires_at is predictable."""
    monkeypatch.setenv("BC_REFRESH_TTL_SECONDS", "3600")
    monkeypatch.setenv("BC_SESSION_TTL_SECONDS", "60")
    from app.config import get_settings

    get_settings.cache_clear()


async def test_create_persists_row_and_returns_tokens() -> None:
    """SessionStore.create stores the HMAC hash and returns distinct tokens."""
    user = _make_user()
    db = _FakeDB(user)
    store = SessionStore(db)  # type: ignore[arg-type]

    tokens = await store.create(user, ip="1.2.3.4", user_agent="pytest")

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.csrf_token
    assert tokens.session_id in db.sessions

    stored = db.sessions[tokens.session_id]
    assert stored.refresh_token_hash == hmac_lookup_hash(tokens.refresh_token.encode("utf-8"))
    assert stored.csrf_token == tokens.csrf_token
    assert stored.revoked_at is None


async def test_refresh_rotates_tokens_and_revokes_old_row() -> None:
    """A refresh call revokes the old row and issues a fresh bundle."""
    user = _make_user()
    db = _FakeDB(user)
    store = SessionStore(db)  # type: ignore[arg-type]

    first = await store.create(user, ip=None, user_agent=None)
    second = await store.refresh(first.refresh_token)

    assert second.session_id != first.session_id
    assert second.refresh_token != first.refresh_token

    old_row = db.sessions[first.session_id]
    assert old_row.revoked_at is not None

    new_row = db.sessions[second.session_id]
    assert new_row.revoked_at is None


async def test_refresh_rejects_unknown_token() -> None:
    """Unknown refresh tokens raise AUTH_002."""
    user = _make_user()
    db = _FakeDB(user)
    store = SessionStore(db)  # type: ignore[arg-type]

    with pytest.raises(UnauthenticatedError) as excinfo:
        await store.refresh("garbage-token")
    assert excinfo.value.code == "AUTH_002"


async def test_refresh_rejects_expired_row() -> None:
    """Expired session rows are rejected with AUTH_002."""
    user = _make_user()
    db = _FakeDB(user)
    store = SessionStore(db)  # type: ignore[arg-type]
    tokens = await store.create(user, ip=None, user_agent=None)

    # Reason: backdate the absolute expiry so the next refresh rejects.
    db.sessions[tokens.session_id].absolute_expires_at = datetime.now(tz=timezone.utc) - timedelta(
        seconds=1
    )
    with pytest.raises(UnauthenticatedError) as excinfo:
        await store.refresh(tokens.refresh_token)
    assert excinfo.value.code == "AUTH_002"


async def test_revoke_marks_revoked_at() -> None:
    """revoke() sets revoked_at on the row."""
    user = _make_user()
    db = _FakeDB(user)
    store = SessionStore(db)  # type: ignore[arg-type]

    tokens = await store.create(user, ip=None, user_agent=None)
    await store.revoke(tokens.session_id)
    assert db.sessions[tokens.session_id].revoked_at is not None


async def test_get_active_ignores_revoked_sessions() -> None:
    """A revoked session is not returned by get_active."""
    user = _make_user()
    db = _FakeDB(user)
    store = SessionStore(db)  # type: ignore[arg-type]

    tokens = await store.create(user, ip=None, user_agent=None)
    assert await store.get_active(tokens.session_id) is not None
    await store.revoke(tokens.session_id)
    assert await store.get_active(tokens.session_id) is None
