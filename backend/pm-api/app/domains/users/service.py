"""Business rules for managing people.

Who may do what:
  * admin     - everything: create, edit any field, reset passwords, archive.
  * manager   - see everyone who is not an admin; edit name, email and job title of direct reports.
  * employee  - edit own name and email (via ``update_me``).
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg

from app.core import dates, security
from app.core.deps import CurrentUser
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.domains.assignments import repository as assignments_repo
from app.domains.projects import repository as projects_repo
from app.domains.users import repository as users_repo
from app.domains.users.schemas import (
    ProfileUpdate,
    UserCreate,
    UserCreated,
    UserList,
    UserOut,
    UserUpdate,
)

_MANAGER_EDITABLE = {"name", "email", "job_title"}


def present(row: dict[str, Any], viewer: CurrentUser) -> UserOut:
    """Build the API shape of a user; only admins and the person themselves see the salary."""
    out = UserOut.model_validate(row)
    if not (viewer.is_admin or viewer.id == row["id"]):
        out = out.model_copy(update={"salary": None})
    return out


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(message, details=[{"field": field, "message": message}])


def _require_active_manager(conn: psycopg.Connection[Any], manager_id: uuid.UUID) -> dict[str, Any]:
    row = users_repo.get_by_id(conn, manager_id)
    if row is None or row["archived_at"] is not None or row["role"] != "manager":
        raise _field_error("manager_id", "The manager must be an active user with the manager role")
    return row


def _check_reporting_line(
    conn: psycopg.Connection[Any], role: str, manager_id: uuid.UUID | None, user_id: uuid.UUID | None
) -> None:
    """Validate the role / manager combination and refuse reporting loops."""
    if role == "employee" and manager_id is None:
        raise _field_error("manager_id", "An employee must report to a manager")
    if role == "admin" and manager_id is not None:
        raise _field_error("manager_id", "Admins do not report to a manager")
    if manager_id is None:
        return
    boss = _require_active_manager(conn, manager_id)
    if user_id is None:
        return
    # Walk up the chain: nobody may end up (indirectly) reporting to themselves.
    seen = {user_id}
    while boss is not None:
        if boss["id"] in seen:
            raise _field_error("manager_id", "That would make a reporting loop")
        seen.add(boss["id"])
        boss = users_repo.get_by_id(conn, boss["manager_id"]) if boss["manager_id"] else None


def _check_email_free(conn: psycopg.Connection[Any], email: str, exclude: uuid.UUID | None = None) -> None:
    if users_repo.email_exists(conn, email, exclude_id=exclude):
        raise ConflictError("Another account already uses that email address", details=[
            {"field": "email", "message": "Already in use"}])


def _load(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> dict[str, Any]:
    row = users_repo.get_by_id(conn, user_id)
    if row is None:
        raise NotFoundError("User not found")
    return row


def list_users(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    *,
    q: str | None,
    role: str | None,
    manager_id: uuid.UUID | None,
    include_archived: bool,
) -> UserList:
    """People the actor may see. Managers never see admins or archived accounts."""
    if actor.is_admin:
        rows = users_repo.list_users(conn, q=q, role=role, manager_id=manager_id, include_archived=include_archived)
    else:
        rows = users_repo.list_users(
            conn, q=q, role=role, manager_id=manager_id, include_archived=False, exclude_roles=["admin"]
        )
    return UserList(items=[present(r, actor) for r in rows], total=len(rows))


def get_user(conn: psycopg.Connection[Any], actor: CurrentUser, user_id: uuid.UUID) -> UserOut:
    """One person; admins see everyone, managers see non-admins, employees only themselves."""
    row = _load(conn, user_id)
    if actor.is_admin or actor.id == user_id:
        return present(row, actor)
    if actor.is_manager and row["role"] != "admin" and row["archived_at"] is None:
        return present(row, actor)
    raise NotFoundError("User not found")


def create_user(conn: psycopg.Connection[Any], actor: CurrentUser, payload: UserCreate) -> UserCreated:
    """Admin creates an account with a generated username and one-time password."""
    _check_reporting_line(conn, payload.role, payload.manager_id, None)
    _check_email_free(conn, payload.email)

    temporary_password = security.generate_password()
    password_hash = security.hash_password(temporary_password)
    for _ in range(20):
        username = security.generate_username(payload.name)
        if not users_repo.username_exists(conn, username):
            break
    else:  # pragma: no cover - 36**4 combinations per prefix
        raise ConflictError("Could not generate a free username, please retry")

    row = users_repo.insert(
        conn,
        username=username,
        password_hash=password_hash,
        name=payload.name,
        email=payload.email,
        job_title=payload.job_title,
        role=payload.role,
        manager_id=payload.manager_id,
        salary=payload.salary,
    )
    return UserCreated(user=present(row, actor), temporary_password=temporary_password)


def update_user(conn: psycopg.Connection[Any], actor: CurrentUser, user_id: uuid.UUID, payload: UserUpdate) -> UserOut:
    """Admins edit anything; managers edit name, email and job title of their direct reports."""
    target = _load(conn, user_id)
    fields = payload.model_dump(exclude_unset=True)
    # An explicit null on a field that cannot be empty is a mistake, not "leave unchanged".
    for required in ("name", "email", "job_title", "role", "salary"):
        if required in fields and fields[required] is None:
            raise _field_error(required, "This field cannot be empty")

    if not actor.is_admin:
        if not actor.is_manager:
            raise ForbiddenError()
        if target["manager_id"] != actor.id or target["archived_at"] is not None:
            raise ForbiddenError("You can only edit people who report to you")
        if set(fields) - _MANAGER_EDITABLE:
            raise ForbiddenError("Only an admin can change role, manager or salary")

    if "email" in fields and fields["email"].lower() != target["email"].lower():
        _check_email_free(conn, fields["email"], exclude=user_id)

    if actor.is_admin and ({"role", "manager_id"} & set(fields)):
        new_role = fields.get("role", target["role"])
        new_manager = fields["manager_id"] if "manager_id" in fields else target["manager_id"]
        if new_role == "admin":
            new_manager = None  # admins sit outside the reporting chain
        if new_role != target["role"]:
            _check_role_change(conn, actor, target, new_role)
        _check_reporting_line(conn, new_role, new_manager, user_id)
        fields["role"], fields["manager_id"] = new_role, new_manager

    row = users_repo.update(conn, user_id, fields)
    if row is None:  # pragma: no cover - loaded a moment ago
        raise NotFoundError("User not found")
    return present(row, actor)


def _check_role_change(conn: psycopg.Connection[Any], actor: CurrentUser, target: dict[str, Any], new_role: str) -> None:
    if target["id"] == actor.id:
        raise _field_error("role", "You cannot change your own role")
    if target["role"] == "admin" and users_repo.count_by_role(conn, "admin") < 2:
        raise ConflictError("There must always be at least one active admin")
    if target["role"] == "manager":
        _ensure_manager_is_free(conn, target["id"], "change the role of")


def _ensure_manager_is_free(conn: psycopg.Connection[Any], manager_id: uuid.UUID, verb: str) -> None:
    projects = projects_repo.count_open_owned(conn, manager_id)
    if projects:
        raise ConflictError(f"Cannot {verb} a manager who still owns {projects} project(s). Reassign or archive them first.")
    reports = users_repo.list_users(conn, manager_id=manager_id)
    if reports:
        raise ConflictError(
            f"Cannot {verb} a manager who still has {len(reports)} direct report(s). Move them to another manager first."
        )


def update_me(conn: psycopg.Connection[Any], actor: CurrentUser, payload: ProfileUpdate) -> UserOut:
    """Anyone may change their own name and email."""
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is None:
            raise _field_error(key, "This field cannot be empty")
    if "email" in fields:
        _check_email_free(conn, fields["email"], exclude=actor.id)
    row = users_repo.update(conn, actor.id, fields)
    if row is None:  # pragma: no cover - the caller was just authenticated
        raise NotFoundError("User not found")
    return present(row, actor)


def reset_password(conn: psycopg.Connection[Any], user_id: uuid.UUID) -> str:
    """Admin sets a new one-time password; the person must change it at next login."""
    _load(conn, user_id)
    temporary_password = security.generate_password()
    users_repo.set_password(conn, user_id, security.hash_password(temporary_password), must_change_password=True)
    return temporary_password


def archive_user(conn: psycopg.Connection[Any], actor: CurrentUser, user_id: uuid.UUID) -> UserOut:
    """Admin archives an account (nothing is ever deleted)."""
    target = _load(conn, user_id)
    if target["archived_at"] is not None:
        return present(target, actor)
    if user_id == actor.id:
        raise ValidationError("You cannot archive your own account")
    if target["role"] == "admin" and users_repo.count_by_role(conn, "admin") < 2:
        raise ConflictError("There must always be at least one active admin")
    if target["role"] == "manager":
        _ensure_manager_is_free(conn, user_id, "archive")
    row = users_repo.set_archived(conn, user_id, archived=True)
    assignments_repo.end_for_user(conn, user_id, dates.today())
    if row is None:  # pragma: no cover - loaded a moment ago
        raise NotFoundError("User not found")
    return present(row, actor)


def unarchive_user(conn: psycopg.Connection[Any], actor: CurrentUser, user_id: uuid.UUID) -> UserOut:
    """Admin restores an archived account (project assignments stay archived)."""
    target = _load(conn, user_id)
    if target["archived_at"] is None:
        return present(target, actor)
    if target["role"] == "employee" and target["manager_id"] is not None:
        _require_active_manager(conn, target["manager_id"])
    row = users_repo.set_archived(conn, user_id, archived=False)
    if row is None:  # pragma: no cover - loaded a moment ago
        raise NotFoundError("User not found")
    return present(row, actor)
