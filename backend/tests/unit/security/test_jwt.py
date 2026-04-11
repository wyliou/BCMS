"""Unit tests for :mod:`app.core.security.jwt`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.errors import UnauthenticatedError
from app.core.security import jwt as jwt_mod
from app.core.security.jwt import decode_access_token, encode_access_token
from app.core.security.roles import Role


def test_encode_decode_round_trip() -> None:
    """Encoding and decoding preserves the identity claims."""
    user_id = uuid4()
    org_id = uuid4()
    token = encode_access_token(user_id, Role.FinanceAdmin, org_id, ttl_seconds=60)
    claims = decode_access_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["role"] == "FinanceAdmin"
    assert claims["org_unit_id"] == str(org_id)


def test_decode_expired_token_raises_auth_002(monkeypatch: pytest.MonkeyPatch) -> None:
    """An expired token raises UnauthenticatedError(AUTH_002)."""
    past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(jwt_mod, "now_utc", lambda: past)
    token = encode_access_token(uuid4(), Role.FinanceAdmin, None, ttl_seconds=1)
    # Reason: jump the clock forward past the TTL to trigger expiry.
    monkeypatch.setattr(jwt_mod, "now_utc", lambda: past + timedelta(hours=2))
    with pytest.raises(UnauthenticatedError) as excinfo:
        decode_access_token(token)
    assert excinfo.value.code == "AUTH_002"


def test_decode_tampered_signature_raises_auth_002() -> None:
    """Flipping a character in the token invalidates the signature."""
    token = encode_access_token(uuid4(), Role.FinanceAdmin, None, ttl_seconds=60)
    tampered = token[:-4] + ("A" if token[-1] != "A" else "B") + token[-3:]
    with pytest.raises(UnauthenticatedError) as excinfo:
        decode_access_token(tampered)
    assert excinfo.value.code == "AUTH_002"
