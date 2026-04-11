"""Unit tests for :mod:`app.domain.cycles.state_machine`."""

from __future__ import annotations

import pytest

from app.core.errors import ConflictError
from app.domain.cycles.models import CycleState
from app.domain.cycles.state_machine import assert_transition, can_transition

ALLOWED: list[tuple[CycleState, CycleState]] = [
    (CycleState.draft, CycleState.open),
    (CycleState.open, CycleState.closed),
    (CycleState.closed, CycleState.open),
]

DENIED: list[tuple[CycleState, CycleState]] = [
    (CycleState.draft, CycleState.draft),
    (CycleState.draft, CycleState.closed),
    (CycleState.open, CycleState.draft),
    (CycleState.open, CycleState.open),
    (CycleState.closed, CycleState.draft),
    (CycleState.closed, CycleState.closed),
]


@pytest.mark.parametrize("src,dst", ALLOWED)
def test_can_transition_allowed(src: CycleState, dst: CycleState) -> None:
    """Every edge in the allowed set returns ``True``."""
    assert can_transition(src, dst) is True


@pytest.mark.parametrize("src,dst", DENIED)
def test_can_transition_denied(src: CycleState, dst: CycleState) -> None:
    """Every other edge returns ``False``."""
    assert can_transition(src, dst) is False


@pytest.mark.parametrize("src,dst", ALLOWED)
def test_assert_transition_allowed(src: CycleState, dst: CycleState) -> None:
    """:func:`assert_transition` is a no-op for allowed edges."""
    assert_transition(src, dst)


@pytest.mark.parametrize("src,dst", DENIED)
def test_assert_transition_denied_raises_cycle_003(src: CycleState, dst: CycleState) -> None:
    """:func:`assert_transition` raises ``ConflictError('CYCLE_003')`` otherwise."""
    with pytest.raises(ConflictError) as exc_info:
        assert_transition(src, dst)
    assert exc_info.value.code == "CYCLE_003"
