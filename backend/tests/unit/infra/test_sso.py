"""Unit tests for :mod:`app.infra.sso`."""

from __future__ import annotations

import pytest

from app.core.errors import InfraError
from app.infra.sso import FakeSSO, OIDCClient, SSOClient


async def test_fake_sso_exchange_and_userinfo() -> None:
    """Happy-path FakeSSO returns the configured payload."""
    fake = FakeSSO(userinfo={"sub": "abc", "email": "a@x", "name": "A", "groups": []})
    tokens = await fake.exchange_code("code")
    assert "access_token" in tokens
    info = await fake.fetch_userinfo(tokens["access_token"])
    assert info["sub"] == "abc"


async def test_fake_sso_auth_001_failure() -> None:
    """``AUTH_001`` path is raised when configured."""
    fake = FakeSSO(should_fail_auth_001=True)
    with pytest.raises(InfraError) as excinfo:
        await fake.exchange_code("code")
    assert excinfo.value.code == "AUTH_001"


async def test_fake_sso_auth_002_failure() -> None:
    """``AUTH_002`` path is raised when configured."""
    fake = FakeSSO(should_fail_auth_002=True)
    with pytest.raises(InfraError) as excinfo:
        await fake.exchange_code("code")
    assert excinfo.value.code == "AUTH_002"


def test_fake_sso_implements_protocol() -> None:
    """FakeSSO satisfies the :class:`SSOClient` protocol."""
    fake = FakeSSO()
    assert isinstance(fake, SSOClient)


def test_oidc_client_constructs_without_network() -> None:
    """Constructing the real client must not trigger network I/O."""
    client = OIDCClient()
    assert client is not None


async def test_oidc_client_missing_discovery_raises() -> None:
    """Missing discovery URL raises ``AUTH_001``."""
    client = OIDCClient()
    with pytest.raises(InfraError):
        await client.exchange_code("code")
