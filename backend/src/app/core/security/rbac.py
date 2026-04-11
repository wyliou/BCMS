"""Role-Based Access Control dependencies (CR-011, CR-032, CR-033).

Role × resource matrix
======================

This matrix is the canonical source of truth for FR-022. Keep it in
sync with PRD §5 and architecture §5.

+---------------------+-------------------------+--------------------------------+
| Role                | Scope semantics         | Notes                          |
+=====================+=========================+================================+
| SystemAdmin         | ALL org units           | Full CRUD — user admin, org    |
|                     |                         | admin, cycles, reopen window.  |
+---------------------+-------------------------+--------------------------------+
| FinanceAdmin        | ALL org units           | Global dashboard + report +    |
|                     |                         | resubmit. Cannot reopen.       |
+---------------------+-------------------------+--------------------------------+
| HRAdmin             | ALL org units           | Read-only to personnel import; |
|                     |                         | may upload personnel budget.   |
+---------------------+-------------------------+--------------------------------+
| FilingUnitManager   | {user.org_unit_id}      | Scoped to a single filing unit |
|                     |                         | (4000–0500 level codes).       |
+---------------------+-------------------------+--------------------------------+
| UplineReviewer      | {user.org_unit_id}      | + every descendant via         |
|                     | ∪ descendants           | recursive parent_id walk.      |
+---------------------+-------------------------+--------------------------------+
| CompanyReviewer     | {root (0000公司)}       | Summary/report only; dashboard |
|                     |                         | items deliberately empty.      |
+---------------------+-------------------------+--------------------------------+
| ITSecurityAuditor   | ALL org units           | Audit log read only.           |
+---------------------+-------------------------+--------------------------------+

RBAC failure codes
==================

``RBAC_001`` — role mismatch (e.g. a filing-unit manager calling a
finance-only route). Raised by :func:`require_role`.

``RBAC_002`` — scope mismatch (e.g. a filing-unit manager attempting
to access a different unit via the URL). Raised by :func:`require_scope`.

Per CR-032, route handlers that carry a resource id in the path MUST
declare BOTH ``require_role`` and ``require_scope`` — ``require_role``
alone is insufficient for scoped resources.

Per CR-033, list endpoints without a path id MUST still pass the result
of :func:`scoped_org_units` as a WHERE filter; the helper intentionally
returns a :class:`frozenset` / :class:`set` that is cheap to combine into
any ORM query.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security.models import OrgUnit, User
from app.core.security.roles import ResourceType, Role
from app.infra.db.session import get_session

__all__ = [
    "ALL_SCOPES",
    "require_role",
    "require_scope",
    "scoped_org_units",
]


#: Sentinel meaning "no scope filter — every org unit is visible".
#: :func:`scoped_org_units` returns this for the three global roles
#: (SystemAdmin, FinanceAdmin, HRAdmin, ITSecurityAuditor). Callers that
#: translate the return value into a SQL ``IN`` clause should check
#: ``if scope is ALL_SCOPES`` first and skip the ``WHERE`` clause.
ALL_SCOPES: Final[frozenset[UUID]] = frozenset()


_GLOBAL_ROLES: frozenset[Role] = frozenset(
    {Role.SystemAdmin, Role.FinanceAdmin, Role.HRAdmin, Role.ITSecurityAuditor}
)


# ---------------------------------------------------------------------------
# Role-only dependency
# ---------------------------------------------------------------------------
def require_role(*roles: Role) -> Callable[..., Awaitable[User]]:
    """FastAPI Depends factory that enforces role membership.

    Args:
        *roles: One or more roles that are permitted to call the route.

    Returns:
        Callable: An async dependency that returns the authenticated
        :class:`User` when its primary role is one of ``roles``.

    Raises:
        ForbiddenError: ``RBAC_001`` when the user's role is not in the
            allowed set. The route layer's global audit middleware
            records ``AuditAction.RBAC_DENIED`` on the way out.
    """
    allowed: frozenset[Role] = frozenset(roles)

    async def _dep(
        request: Request,
        db: AsyncSession = Depends(get_session),
    ) -> User:
        """Resolve the current user and enforce the role check."""
        # Reason: the lazy import avoids a module-import cycle with
        # ``auth_service`` (which imports ``require_role`` indirectly via
        # ``api.v1.auth`` helpers in some test fixtures).
        from app.core.security.auth_service import AuthService

        service = AuthService(db)
        user = await service.current_user(request)
        user_roles = user.role_set()
        if not user_roles.intersection(allowed):
            raise ForbiddenError(
                "RBAC_001",
                f"Role not permitted: need any of {sorted(r.value for r in allowed)}",
            )
        return user

    return _dep


# ---------------------------------------------------------------------------
# Scope dependency
# ---------------------------------------------------------------------------
def require_scope(
    resource_type: ResourceType | str,
    resource_id_param: str,
) -> Callable[..., Awaitable[None]]:
    """FastAPI Depends factory that enforces per-org-unit scope.

    Args:
        resource_type: :class:`ResourceType` member (or its raw string
            value) describing what the resource id represents. Included
            in the :class:`ForbiddenError` message for auditability.
        resource_id_param: Name of the path parameter that holds the
            target resource id.

    Returns:
        Callable: An async dependency that raises on scope mismatch.

    Raises:
        ForbiddenError: ``RBAC_002`` when the resolved resource id is
            not in the user's :func:`scoped_org_units` result.
    """
    resource_key = (
        resource_type.value if isinstance(resource_type, ResourceType) else str(resource_type)
    )

    async def _dep(
        request: Request,
        db: AsyncSession = Depends(get_session),
    ) -> None:
        """Resolve the current user and enforce the scope check."""
        from app.core.security.auth_service import AuthService

        service = AuthService(db)
        user = await service.current_user(request)

        raw_value = request.path_params.get(resource_id_param)
        if raw_value is None:
            raise ForbiddenError(
                "RBAC_002",
                f"Resource id parameter {resource_id_param!r} missing",
            )
        try:
            target_id = UUID(str(raw_value))
        except ValueError as exc:
            raise ForbiddenError(
                "RBAC_002",
                f"Resource id {raw_value!r} is not a UUID",
            ) from exc

        scope = await scoped_org_units(user, db)
        if scope is ALL_SCOPES:
            return
        if target_id not in scope:
            raise ForbiddenError(
                "RBAC_002",
                f"{resource_key} {target_id} outside permitted scope",
            )

    return _dep


# ---------------------------------------------------------------------------
# Scope query
# ---------------------------------------------------------------------------
async def scoped_org_units(user: User, db: AsyncSession) -> frozenset[UUID] | set[UUID]:
    """Return the set of ``org_unit_id`` values visible to ``user``.

    Global roles (``SystemAdmin``, ``FinanceAdmin``, ``HRAdmin``,
    ``ITSecurityAuditor``) receive the :data:`ALL_SCOPES` sentinel so
    the caller can skip the ``WHERE org_unit_id IN (...)`` clause
    entirely. Every other role returns a materialized :class:`set`.

    Args:
        user (User): Authenticated user.
        db (AsyncSession): Active database session (used by
            :class:`UplineReviewer` to walk the org tree).

    Returns:
        frozenset[UUID] | set[UUID]: Visible org-unit ids, or
        :data:`ALL_SCOPES` (empty frozenset sentinel) for global roles.
    """
    roles = user.role_set()
    if roles.intersection(_GLOBAL_ROLES):
        return ALL_SCOPES

    if Role.CompanyReviewer in roles:
        # Reason: 0000公司 has level_code "0000" and is the logical root
        # for the consolidated report. Return just that org unit.
        stmt = select(OrgUnit.id).where(OrgUnit.level_code == "0000")
        result = await db.execute(stmt)
        return {row[0] for row in result.all()}

    if Role.FilingUnitManager in roles:
        return {user.org_unit_id} if user.org_unit_id is not None else set()

    if Role.UplineReviewer in roles:
        if user.org_unit_id is None:
            return set()
        return await _descendants(db, user.org_unit_id)

    return set()


async def _descendants(db: AsyncSession, root_id: UUID) -> set[UUID]:
    """Return ``root_id`` plus every transitive descendant in ``org_units``.

    Walks the ``parent_id`` column iteratively because the portable
    SQLAlchemy core does not expose a clean recursive-CTE builder on
    SQLite (used by the unit-test tier). The iteration is bounded by
    the fixed org-tree depth from PRD §1.2 so this is effectively
    O(depth) regardless of branching.

    Args:
        db (AsyncSession): Active database session.
        root_id (UUID): Starting org-unit id.

    Returns:
        set[UUID]: ``{root_id}`` plus every descendant id.
    """
    visited: set[UUID] = {root_id}
    frontier: set[UUID] = {root_id}
    while frontier:
        stmt = select(OrgUnit.id).where(OrgUnit.parent_id.in_(frontier))
        result = await db.execute(stmt)
        next_frontier: set[UUID] = set()
        for (child_id,) in result.all():
            if child_id not in visited:
                visited.add(child_id)
                next_frontier.add(child_id)
        frontier = next_frontier
    return visited
