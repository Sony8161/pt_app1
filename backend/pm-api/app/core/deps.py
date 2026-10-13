"""
FastAPI dependencies: database access, the authenticated user and role checks.

Permission checks are centralised here (``require_roles``) and in the domain
services; routers never inspect roles ad hoc.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

import psycopg
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AuthError, ForbiddenError
from app.core.security import decode_access_token
from app.db import ensure_migrated, get_connection
from app.domains.users import repository as users_repo

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_EMPLOYEE = "employee"
ALL_ROLES = (ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE)

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated caller, as loaded from the database on every request."""

    id: uuid.UUID
    username: str
    name: str
    email: str
    role: str
    manager_id: uuid.UUID | None
    must_change_password: bool

    @property
    def is_admin(self) -> bool:
        """True for the admin role."""
        return self.role == ROLE_ADMIN

    @property
    def is_manager(self) -> bool:
        """True for the manager role."""
        return self.role == ROLE_MANAGER


def get_db() -> psycopg.Connection[Any]:
    """Shared connection for the current request (transaction managed by middleware)."""
    conn = get_connection()
    ensure_migrated(conn)
    return conn


DbConn = Annotated[psycopg.Connection[Any], Depends(get_db)]


def get_authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    conn: DbConn,
) -> CurrentUser:
    """Resolve the bearer token to an active user (password-change state not enforced)."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthError("Authentication required")

    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise AuthError("Invalid authentication token", code="token_invalid") from exc

    row = users_repo.get_by_id(conn, user_id)
    if row is None or row["archived_at"] is not None:
        raise AuthError("This account is no longer active", code="account_inactive")
    if row["token_version"] != claims.get("tv"):
        raise AuthError("Your session is no longer valid. Please sign in again.", code="token_revoked")

    return CurrentUser(
        id=row["id"],
        username=row["username"],
        name=row["name"],
        email=row["email"],
        role=row["role"],
        manager_id=row["manager_id"],
        must_change_password=row["must_change_password"],
    )


def get_current_user(user: Annotated[CurrentUser, Depends(get_authenticated_user)]) -> CurrentUser:
    """Authenticated user who has also completed any required password change."""
    if user.must_change_password:
        raise ForbiddenError("You must change your password before continuing", code="password_change_required")
    return user


def require_roles(*roles: str) -> Callable[..., CurrentUser]:
    """Dependency factory restricting an endpoint to the given roles."""

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in roles:
            raise ForbiddenError()
        return user

    return dependency


AuthenticatedUser = Annotated[CurrentUser, Depends(get_authenticated_user)]
ActiveUser = Annotated[CurrentUser, Depends(get_current_user)]
AdminUser = Annotated[CurrentUser, Depends(require_roles(ROLE_ADMIN))]
ManagerOrAdmin = Annotated[CurrentUser, Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER))]
