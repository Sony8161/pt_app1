"""HTTP endpoints for authentication."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.deps import AuthenticatedUser, DbConn
from app.core.errors import AuthError
from app.domains.auth import service
from app.domains.auth.schemas import ChangePasswordRequest, LoginRequest, TokenResponse
from app.domains.users import repository as users_repo
from app.domains.users.schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(payload: LoginRequest, conn: DbConn) -> TokenResponse:
    """Exchange username and password for an access token."""
    return service.login(conn, payload.username, payload.password)


@router.get("/me", response_model=UserOut)
def me(user: AuthenticatedUser, conn: DbConn) -> UserOut:
    """Profile of the caller (available even while a password change is pending)."""
    row = users_repo.get_by_id(conn, user.id)
    if row is None:  # pragma: no cover - the dependency just loaded this user
        raise AuthError("This account is no longer active", code="account_inactive")
    return UserOut.model_validate(row)


@router.post("/refresh", response_model=TokenResponse)
def refresh(user: AuthenticatedUser, conn: DbConn) -> TokenResponse:
    """Issue a fresh token for a still-valid session."""
    return service.refresh(conn, user)


@router.post("/change-password", response_model=TokenResponse)
def change_password(payload: ChangePasswordRequest, user: AuthenticatedUser, conn: DbConn) -> TokenResponse:
    """Change the caller's password and return a new token (previous tokens are revoked)."""
    return service.change_password(conn, user, payload.current_password, payload.new_password)
