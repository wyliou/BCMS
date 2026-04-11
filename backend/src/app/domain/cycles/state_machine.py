"""State-machine helpers for :class:`BudgetCycle`.

Encodes FR-006 and CR-005: the only legal transitions are

``draft → open``,
``open → closed``, and
``closed → open`` (reopen window, CR-037 enforcement lives in
:meth:`CycleService.reopen`).

Every other transition is rejected with ``ConflictError('CYCLE_003')``. The
service layer calls :func:`assert_transition` before mutating the row and
writing the audit trail.
"""

from __future__ import annotations

from app.core.errors import ConflictError
from app.domain.cycles.models import CycleState

__all__ = ["can_transition", "assert_transition"]


# Explicit allowed-edge set; anything absent is a denial.
_ALLOWED: frozenset[tuple[CycleState, CycleState]] = frozenset(
    {
        (CycleState.draft, CycleState.open),
        (CycleState.open, CycleState.closed),
        (CycleState.closed, CycleState.open),
    }
)


def can_transition(from_state: CycleState, to_state: CycleState) -> bool:
    """Return whether ``from_state → to_state`` is a legal cycle transition.

    Args:
        from_state: Current cycle state.
        to_state: Target cycle state.

    Returns:
        bool: ``True`` when the transition is legal, ``False`` otherwise.
    """
    return (from_state, to_state) in _ALLOWED


def assert_transition(from_state: CycleState, to_state: CycleState) -> None:
    """Raise :class:`ConflictError` (``CYCLE_003``) when the transition is illegal.

    Args:
        from_state: Current cycle state.
        to_state: Target cycle state.

    Raises:
        ConflictError: ``CYCLE_003`` when :func:`can_transition` returns
            ``False``. The message includes the illegal edge so the caller
            can attach additional context if needed.
    """
    if not can_transition(from_state, to_state):
        raise ConflictError(
            "CYCLE_003",
            f"Cycle cannot transition from {from_state.value!r} to {to_state.value!r}",
        )
