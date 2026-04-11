"""Unit tests for :class:`app.domain.audit.service.AuditService`.

These tests exercise the real service and real hash-chain primitives
against an in-memory repo double (see ``conftest.py``). The only thing
that is substituted is the repo — the service, hash chain, and payload
serialization run for real.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.domain.audit.actions import AuditAction
from app.domain.audit.models import AuditLog
from app.domain.audit.repo import AuditFilters
from app.domain.audit.service import _GENESIS_PREV_HASH, AuditService
from app.infra.crypto import chain_hash


# ---------------------------------------------------------------- record()
async def test_record_first_row_uses_genesis_prev_hash(audit_service_and_repo) -> None:
    """The very first row should use the 32-byte zero sentinel."""
    service, repo = audit_service_and_repo
    row = await service.record(
        action=AuditAction.LOGIN_SUCCESS,
        resource_type="session",
        details={"username": "alice"},
    )
    assert row.prev_hash == _GENESIS_PREV_HASH
    assert len(row.hash_chain_value) == 32
    assert len(repo.rows) == 1


async def test_record_second_row_uses_previous_hash(audit_service_and_repo) -> None:
    """The second row's ``prev_hash`` should equal the first row's chain value."""
    service, _repo = audit_service_and_repo
    first = await service.record(
        action=AuditAction.LOGIN_SUCCESS,
        resource_type="session",
        details={"u": 1},
    )
    second = await service.record(
        action=AuditAction.LOGOUT,
        resource_type="session",
        details={"u": 1},
    )
    assert second.prev_hash == first.hash_chain_value
    assert second.sequence_no == first.sequence_no + 1


async def test_record_computes_expected_chain_hash(audit_service_and_repo) -> None:
    """The stored hash matches a direct ``chain_hash`` invocation."""
    service, _repo = audit_service_and_repo
    row = await service.record(
        action=AuditAction.CYCLE_OPEN,
        resource_type="cycle",
        resource_id=uuid4(),
        user_id=uuid4(),
        ip_address="10.0.0.1",
        details={"note": "ok"},
    )
    expected = chain_hash(row.prev_hash, AuditService._serialize_for_chain(row))
    assert row.hash_chain_value == expected


async def test_record_canonical_payload_is_deterministic(
    audit_service_and_repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Freezing the clock makes two identical records produce the same payload."""
    import app.domain.audit.service as svc_mod

    fixed = datetime(2026, 4, 12, 1, 2, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(svc_mod, "now_utc", lambda: fixed)

    service, _repo = audit_service_and_repo
    user_id = uuid4()
    resource_id = uuid4()

    row_a = await service.record(
        action=AuditAction.LOGIN_SUCCESS,
        resource_type="session",
        resource_id=resource_id,
        user_id=user_id,
        ip_address="10.0.0.1",
        details={"b": 2, "a": 1},
    )
    payload_a = AuditService._serialize_for_chain(row_a)

    # A completely fresh service + repo with the same seq_no should yield
    # the same serialized payload, proving the sort + format is stable.
    from tests.unit.audit.conftest import InMemoryAuditRepo

    fresh_repo = InMemoryAuditRepo()
    fresh_service = AuditService(service._db)
    fresh_service._repo = fresh_repo  # type: ignore[assignment]
    row_b = await fresh_service.record(
        action=AuditAction.LOGIN_SUCCESS,
        resource_type="session",
        resource_id=resource_id,
        user_id=user_id,
        ip_address="10.0.0.1",
        details={"a": 1, "b": 2},
    )
    payload_b = AuditService._serialize_for_chain(row_b)
    assert payload_a == payload_b


# ---------------------------------------------------- _serialize_for_chain
def _build_row(**overrides: object) -> AuditLog:
    """Helper: build an :class:`AuditLog` with canonical defaults."""
    defaults: dict[str, object] = {
        "id": uuid4(),
        "sequence_no": 1,
        "user_id": None,
        "action": "LOGIN_SUCCESS",
        "resource_type": "session",
        "resource_id": None,
        "ip_address": None,
        "details": {},
        "prev_hash": _GENESIS_PREV_HASH,
        "hash_chain_value": _GENESIS_PREV_HASH,
        "occurred_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return AuditLog(**defaults)


def test_serialize_for_chain_sorted_keys() -> None:
    """Serialized JSON has keys in alphabetical order."""
    row = _build_row(details={"z": 1, "a": 2})
    payload = AuditService._serialize_for_chain(row)
    parsed_keys = list(json.loads(payload).keys())
    assert parsed_keys == sorted(parsed_keys)


def test_serialize_for_chain_iso_utc_datetime() -> None:
    """``occurred_at`` is rendered with the ``+00:00`` suffix."""
    row = _build_row(occurred_at=datetime(2026, 4, 12, 1, 2, 3, tzinfo=timezone.utc))
    payload = AuditService._serialize_for_chain(row)
    parsed = json.loads(payload)
    assert parsed["occurred_at"] == "2026-04-12T01:02:03+00:00"


def test_serialize_for_chain_naive_datetime_assumed_utc() -> None:
    """Naive datetimes are normalized to UTC before formatting."""
    row = _build_row(occurred_at=datetime(2026, 4, 12, 1, 2, 3))
    payload = AuditService._serialize_for_chain(row)
    parsed = json.loads(payload)
    assert parsed["occurred_at"].endswith("+00:00")


def test_serialize_for_chain_no_whitespace() -> None:
    """Separators are compact — no extra spaces."""
    row = _build_row(details={"a": 1, "b": 2})
    payload = AuditService._serialize_for_chain(row).decode("utf-8")
    assert ", " not in payload
    assert ": " not in payload


def test_serialize_for_chain_uuid_string_form() -> None:
    """UUID fields are rendered as their canonical hex-dashed string."""
    user = uuid4()
    resource = uuid4()
    row = _build_row(user_id=user, resource_id=resource)
    parsed = json.loads(AuditService._serialize_for_chain(row))
    assert parsed["user_id"] == str(user)
    assert parsed["resource_id"] == str(resource)


# ---------------------------------------------------------- verify_chain()
async def test_verify_chain_empty_range(audit_service_and_repo) -> None:
    """Empty input is considered verified with length 0."""
    service, _repo = audit_service_and_repo
    result = await service.verify_chain()
    assert result.verified is True
    assert result.chain_length == 0
    assert result.failed_at_sequence_no is None


async def test_verify_chain_happy_path(audit_service_and_repo) -> None:
    """A correctly built chain passes verification."""
    service, _repo = audit_service_and_repo
    for i in range(5):
        await service.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            details={"i": i},
        )
    result = await service.verify_chain()
    assert result.verified is True
    assert result.chain_length == 5


async def test_verify_chain_detects_tampered_details(audit_service_and_repo) -> None:
    """Mutating a row's details after the fact breaks the chain."""
    service, repo = audit_service_and_repo
    for i in range(3):
        await service.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            details={"i": i},
        )
    # Tamper in-memory — bypasses REVOKE but simulates a corrupted row.
    repo.rows[1].details = {"tampered": True}

    with pytest.raises(AppError) as exc_info:
        await service.verify_chain()
    assert exc_info.value.code == "AUDIT_001"


async def test_verify_chain_detects_broken_prev_hash(audit_service_and_repo) -> None:
    """A row whose ``prev_hash`` no longer matches the previous row is caught."""
    service, repo = audit_service_and_repo
    for i in range(3):
        await service.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            details={"i": i},
        )
    repo.rows[2].prev_hash = b"\x01" * 32

    with pytest.raises(AppError) as exc_info:
        await service.verify_chain()
    assert exc_info.value.code == "AUDIT_001"


async def test_verify_chain_range_filter(
    audit_service_and_repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A range filter limits the rows to re-verify.

    Uses monkeypatched clock so each row receives a distinct timestamp at
    write time — the chain stays valid because ``occurred_at`` is part of
    the serialized payload.
    """
    import app.domain.audit.service as svc_mod

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = [base + timedelta(days=i) for i in range(4)]
    iterator = iter(times)
    monkeypatch.setattr(svc_mod, "now_utc", lambda: next(iterator))

    service, _repo = audit_service_and_repo
    for i in range(4):
        await service.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            details={"i": i},
        )

    window_start = base + timedelta(days=1)
    window_end = base + timedelta(days=2)
    result = await service.verify_chain(window_start, window_end)
    assert result.verified is True
    # Rows at day 1 and day 2 are inside the inclusive window.
    assert result.chain_length == 2


# ------------------------------------------------------------- query()
async def test_query_filter_by_action(audit_service_and_repo) -> None:
    """Filtering by action returns only matching rows."""
    service, _repo = audit_service_and_repo
    await service.record(action=AuditAction.LOGIN_SUCCESS, resource_type="session", details={})
    await service.record(action=AuditAction.LOGOUT, resource_type="session", details={})
    await service.record(action=AuditAction.LOGIN_SUCCESS, resource_type="session", details={})
    result = await service.query(AuditFilters(action="LOGIN_SUCCESS"))
    assert result.total == 2
    assert all(r.action == "LOGIN_SUCCESS" for r in result.items)


async def test_query_filter_by_time_range(audit_service_and_repo) -> None:
    """A ``from_dt``/``to_dt`` window narrows the result set."""
    service, repo = audit_service_and_repo
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        await service.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            details={"i": i},
        )
        repo.rows[-1].occurred_at = base + timedelta(days=i)

    window_start = base + timedelta(days=1)
    window_end = base + timedelta(days=3)
    result = await service.query(AuditFilters(from_dt=window_start, to_dt=window_end))
    assert result.total == 3


async def test_query_invalid_range_raises_audit_002(audit_service_and_repo) -> None:
    """``to_dt < from_dt`` is a client error and maps to ``AUDIT_002``.

    The in-memory repo delegates validation to the same code path the real
    repo uses — but note that the in-memory fake does not validate. This
    test invokes the real repo's ``_validate_filters`` helper directly.
    """
    from app.domain.audit.repo import AuditRepo

    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(AppError) as exc_info:
        AuditRepo._validate_filters(AuditFilters(from_dt=start, to_dt=end))
    assert exc_info.value.code == "AUDIT_002"
