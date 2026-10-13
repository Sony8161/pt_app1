"""Pydantic models for the auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domains.users.schemas import UserOut


class LoginRequest(BaseModel):
    """Credentials submitted by the login form."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    """Issued access token plus the profile of its owner."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_at: int = Field(description="Expiry as Unix epoch seconds")
    user: UserOut


class ChangePasswordRequest(BaseModel):
    """Self-service password change."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
