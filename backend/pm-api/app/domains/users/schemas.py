"""Pydantic models for users."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

Role = Literal["admin", "manager", "employee"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    value = value.strip()
    if not _EMAIL_RE.match(value):
        raise ValueError("must be a valid email address")
    return value


Email = Annotated[str, Field(max_length=254), AfterValidator(_validate_email)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
JobTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class UserOut(BaseModel):
    """Profile visible to any signed-in user who may see this person."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    name: str
    email: str
    job_title: str
    role: Role
    manager_id: uuid.UUID | None
    must_change_password: bool
    archived_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    salary: float | None = Field(
        default=None,
        description="Hourly cost in dollars per hour. Only admins (and the person themselves) see it.",
    )


class UserCreate(BaseModel):
    """Admin request to create an account. Username and password are generated."""

    name: PersonName
    email: Email
    job_title: JobTitle = ""
    role: Role
    manager_id: uuid.UUID | None = Field(
        default=None, description="Required for employees: the manager they report to"
    )
    salary: float = Field(default=0, ge=0, le=100000, description="Hourly cost, dollars per hour")


class UserCreated(BaseModel):
    """The new account plus its one-time password (shown once, never stored in clear)."""

    user: UserOut
    temporary_password: str


class UserUpdate(BaseModel):
    """Admin edit. Send only the fields to change; ``manager_id: null`` clears the manager."""

    name: PersonName | None = None
    email: Email | None = None
    job_title: JobTitle | None = None
    role: Role | None = None
    manager_id: uuid.UUID | None = None
    salary: float | None = Field(default=None, ge=0, le=100000)


class TeamMemberUpdate(BaseModel):
    """What a manager may change about a direct report."""

    name: PersonName | None = None
    email: Email | None = None
    job_title: JobTitle | None = None


class ProfileUpdate(BaseModel):
    """What anyone may change about themselves."""

    name: PersonName | None = None
    email: Email | None = None


class PasswordReset(BaseModel):
    """Result of an admin password reset."""

    temporary_password: str


class UserList(BaseModel):
    """List response."""

    items: list[UserOut]
    total: int
