"""Admin user-management routes (SystemAdmin only).

Every route in this module is guarded by
``Depends(require_role(Role.SystemAdmin))`` per CR-032. Mutating routes
follow CR-006 (commit state change first, then write the audit row on
a fresh side session).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.infra.db.session import get_session, get_session_factory

__all__ = ["router"]


router = APIRouter(prefix="/admin/users", tags=["admin", "users"])


class UserRead(BaseModel):
    """Serialized user record for the admin UI.

    Attributes:
        id (UUID): User id.
        name (str): Display name.
        roles (list[str]): Raw role values from ``users.roles``.
        org_unit_id (UUID | None): Assigned org unit id.
        is_active (bool): Whether the account is currently active.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    roles: list[str]
    org_unit_id: UUID | None
    is_active: bool


class UsersPage(BaseModel):
    """Paginated response body for ``GET /admin/users``.

    Attributes:
        items (list[UserRead]): Page rows.
        total (int): Total matching rows.
        page (int): Current page (1-based).
        size (int): Page size.
    """

    items: list[UserRead]
    total: int
    page: int
    size: int


class UserPatch(BaseModel):
    """Body accepted by ``PATCH /admin/users/{user_id}``.

    Attributes:
        roles (list[str] | None): New role list; empty list clears.
        org_unit_id (UUID | None): New scoped org-unit id.
    """

    roles: list[str] | None = None
    org_unit_id: UUID | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=UsersPage)
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.SystemAdmin)),
) -> UsersPage:
    """Return a paginated list of users.

    Args:
        page (int): 1-based page number.
        size (int): Page size (max 200).
        db (AsyncSession): Injected DB session.
        _user (User): RBAC guard — SystemAdmin only.

    Returns:
        UsersPage: Paginated slice of the ``users`` table.
    """
    del _user
    count_stmt = select(func.count()).select_from(User)
    list_stmt = select(User).order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = list((await db.execute(list_stmt)).scalars().all())
    return UsersPage(
        items=[UserRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        size=size,
    )


@router.patch("/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: UUID,
    body: UserPatch,
    request: Request,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_role(Role.SystemAdmin)),
) -> UserRead:
    """Update a user's roles and/or org unit assignment.

    Args:
        user_id (UUID): Target user id (path param).
        body (UserPatch): Patch body.
        request (Request): Inbound request (for IP capture).
        db (AsyncSession): Injected DB session.
        actor (User): The SystemAdmin making the change.

    Returns:
        UserRead: The updated user record.
    """
    del request  # reserved for future IP logging hooks
    row = await db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND"}})

    before = {
        "roles": list(row.roles),
        "org_unit_id": str(row.org_unit_id) if row.org_unit_id else None,
    }

    if body.roles is not None:
        # Reason: filter out non-enum role names early so admins can't
        # store garbage in the JSONB array.
        valid: list[str] = []
        for name in body.roles:
            try:
                valid.append(Role(name).value)
            except ValueError:
                continue
        row.roles = valid
    if body.org_unit_id is not None:
        row.org_unit_id = body.org_unit_id
    row.updated_at = now_utc()
    await db.flush()
    await db.commit()

    after = {
        "roles": list(row.roles),
        "org_unit_id": str(row.org_unit_id) if row.org_unit_id else None,
    }
    await _audit_user_role_change(actor.id, row.id, before, after)
    return UserRead.model_validate(row)


@router.post("/{user_id}/deactivate", response_model=UserRead)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_role(Role.SystemAdmin)),
) -> UserRead:
    """Deactivate a user account.

    Args:
        user_id (UUID): Target user id.
        db (AsyncSession): Injected DB session.
        actor (User): The SystemAdmin making the change.

    Returns:
        UserRead: The updated user record with ``is_active=False``.
    """
    row = await db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND"}})

    before: dict[str, object] = {"is_active": row.is_active}
    row.is_active = False
    row.updated_at = now_utc()
    await db.flush()
    await db.commit()
    after: dict[str, object] = {"is_active": row.is_active}
    await _audit_user_role_change(actor.id, row.id, before, after)
    return UserRead.model_validate(row)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _audit_user_role_change(
    actor_id: UUID,
    target_id: UUID,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    """Write a USER_ROLE_UPDATED audit row on a fresh side session (CR-006).

    Args:
        actor_id (UUID): The SystemAdmin performing the update.
        target_id (UUID): The user being modified.
        before (dict[str, object]): Pre-change snapshot.
        after (dict[str, object]): Post-change snapshot.
    """
    factory = get_session_factory()
    async with factory() as db:
        service = AuditService(db)
        await service.record(
            action=AuditAction.USER_ROLE_UPDATED,
            resource_type="user",
            resource_id=target_id,
            user_id=actor_id,
            ip_address=None,
            details={"before": before, "after": after},
        )
        await db.commit()
