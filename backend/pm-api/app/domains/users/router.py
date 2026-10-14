"""HTTP endpoints for people."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.deps import ActiveUser, AdminUser, DbConn, ManagerOrAdmin
from app.domains.users import service
from app.domains.users.schemas import (
    PasswordReset,
    ProfileUpdate,
    Role,
    UserCreate,
    UserCreated,
    UserList,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserList)
def list_users(
    actor: ManagerOrAdmin,
    conn: DbConn,
    q: str | None = None,
    role: Role | None = None,
    manager_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> UserList:
    """Search people by name, email, username or job title. Only admins can include archived accounts."""
    return service.list_users(conn, actor, q=q, role=role, manager_id=manager_id, include_archived=include_archived)


@router.post("", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, actor: AdminUser, conn: DbConn) -> UserCreated:
    """Create an account. The 6-character username and a one-time password are generated."""
    return service.create_user(conn, actor, payload)


@router.patch("/me", response_model=UserOut)
def update_me(payload: ProfileUpdate, actor: ActiveUser, conn: DbConn) -> UserOut:
    """Change your own name or email."""
    return service.update_me(conn, actor, payload)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> UserOut:
    """One person's profile."""
    return service.get_user(conn, actor, user_id)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, payload: UserUpdate, actor: ManagerOrAdmin, conn: DbConn) -> UserOut:
    """Admins edit any field; managers edit name, email and job title of their direct reports."""
    return service.update_user(conn, actor, user_id, payload)


@router.post("/{user_id}/reset-password", response_model=PasswordReset)
def reset_password(user_id: uuid.UUID, actor: AdminUser, conn: DbConn) -> PasswordReset:
    """Generate a new one-time password for someone else; they must change it at next login."""
    return PasswordReset(temporary_password=service.reset_password(conn, actor, user_id))


@router.post("/{user_id}/archive", response_model=UserOut)
def archive_user(user_id: uuid.UUID, actor: AdminUser, conn: DbConn) -> UserOut:
    """Archive an account. Their history is kept."""
    return service.archive_user(conn, actor, user_id)


@router.post("/{user_id}/unarchive", response_model=UserOut)
def unarchive_user(user_id: uuid.UUID, actor: AdminUser, conn: DbConn) -> UserOut:
    """Restore an archived account."""
    return service.unarchive_user(conn, actor, user_id)
