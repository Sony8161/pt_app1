"""Business rules for projects, plus the access helpers every project-scoped domain reuses.

Visibility (a project you may not see is reported as 404, never 403):
  * admin     - every project (archived ones too)
  * manager   - projects they manage
  * employee  - projects they are assigned to
Managing (edit, milestones, team, costs): the admin, or the project's own manager.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg

from app.core import dates
from app.core.deps import CurrentUser
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.domains.assignments import repository as assignments_repo
from app.domains.milestones import repository as milestones_repo
from app.domains.projects import repository as repo
from app.domains.projects.metrics import build_summary
from app.domains.projects.schemas import (
    ManagerRef,
    ProjectCreate,
    ProjectList,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
)
from app.domains.users import repository as users_repo

OPEN_STATUSES = ("planned", "active")


# --------------------------------------------------------------------------- access helpers
def get_visible(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> dict[str, Any]:
    """Project row the actor may see, or 404."""
    row = repo.get(conn, project_id, dates.today())
    if row is None:
        raise NotFoundError("Project not found")
    if actor.is_admin:
        return row
    if row["archived_at"] is not None:
        raise NotFoundError("Project not found")
    if actor.is_manager:
        if row["manager_id"] != actor.id:
            raise NotFoundError("Project not found")
    elif assignments_repo.get_active(conn, project_id, actor.id) is None:
        raise NotFoundError("Project not found")
    return row


def get_manageable(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, *, must_be_open: bool = True
) -> dict[str, Any]:
    """Project row the actor may change (admin or its manager); 403 for other viewers, 409 once finished."""
    row = get_visible(conn, actor, project_id)
    if not (actor.is_admin or row["manager_id"] == actor.id):
        raise ForbiddenError("Only the project's manager or an admin can change this project")
    if must_be_open and row["status"] not in OPEN_STATUSES:
        raise ConflictError(f"This project is {row['status']} and can no longer be changed")
    return row


# --------------------------------------------------------------------------- presentation
def present(row: dict[str, Any], actor: CurrentUser) -> ProjectOut:
    """API shape of a project row; money is hidden from employees."""
    include_costs = actor.role != "employee"
    summary = build_summary(row, dates.today(), include_costs=include_costs)
    return ProjectOut(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        manager=ManagerRef(id=row["manager_id"], name=row["manager_name"]),
        status=row["status"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        allocated_hours=float(row["allocated_hours"]),
        budget_amount=float(row["budget_amount"]) if include_costs else None,
        completed_at=row["completed_at"],
        archived_at=row["archived_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        summary=ProjectSummary(**summary),
    )


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(message, details=[{"field": field, "message": message}])


def _require_active_manager(conn: psycopg.Connection[Any], manager_id: uuid.UUID) -> None:
    row = users_repo.get_by_id(conn, manager_id)
    if row is None or row["archived_at"] is not None or row["role"] != "manager":
        raise _field_error("manager_id", "The project manager must be an active user with the manager role")


# --------------------------------------------------------------------------- use cases
def list_projects(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    *,
    q: str | None,
    status: str | None,
    manager_id: uuid.UUID | None,
    include_archived: bool,
    page: int,
    page_size: int,
) -> ProjectList:
    """Projects the actor may see. Only admins can include archived ones."""
    rows, total = repo.search(
        conn,
        today=dates.today(),
        viewer_id=actor.id,
        viewer_role=actor.role,
        q=q,
        status=status,
        manager_id=manager_id,
        include_archived=include_archived and actor.is_admin,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return ProjectList(items=[present(r, actor) for r in rows], total=total, page=page, page_size=page_size)


def get_project(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> ProjectOut:
    """One project with its health summary."""
    return present(get_visible(conn, actor, project_id), actor)


def _reload(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> ProjectOut:
    row = repo.get(conn, project_id, dates.today())
    if row is None:  # pragma: no cover - the caller just wrote this project
        raise NotFoundError("Project not found")
    return present(row, actor)


def create_project(conn: psycopg.Connection[Any], actor: CurrentUser, payload: ProjectCreate) -> ProjectOut:
    """Admin creates a project for exactly one manager."""
    _require_active_manager(conn, payload.manager_id)
    if repo.name_taken(conn, payload.name):
        raise ConflictError("A project with this name already exists", details=[
            {"field": "name", "message": "Already in use"}])
    project_id = repo.insert(
        conn,
        name=payload.name,
        description=payload.description,
        manager_id=payload.manager_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        allocated_hours=payload.allocated_hours,
        budget_amount=payload.budget_amount,
        created_by=actor.id,
    )
    return _reload(conn, actor, project_id)


def update_project(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, payload: ProjectUpdate
) -> ProjectOut:
    """Admin or the project's manager edits it (budget, hours and dates included)."""
    row = get_manageable(conn, actor, project_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is None:
            raise _field_error(key, "This field cannot be empty")

    if "manager_id" in fields and fields["manager_id"] != row["manager_id"]:
        if not actor.is_admin:
            raise ForbiddenError("Only an admin can change the project's manager")
        _require_active_manager(conn, fields["manager_id"])

    start = fields.get("start_date", row["start_date"])
    end = fields.get("end_date", row["end_date"])
    if end < start:
        raise _field_error("end_date", "The end date must be on or after the start date")
    if "start_date" in fields or "end_date" in fields:
        _check_dates_fit_children(conn, project_id, start, end)

    if "allocated_hours" in fields:
        planned = milestones_repo.hours_total(conn, project_id)
        if planned > fields["allocated_hours"]:
            raise _field_error(
                "allocated_hours",
                f"The milestones already plan {planned:g} hours, more than {fields['allocated_hours']:g}",
            )

    if "name" in fields and fields["name"].lower() != row["name"].lower() and repo.name_taken(
        conn, fields["name"], exclude_id=project_id
    ):
        raise ConflictError("A project with this name already exists", details=[
            {"field": "name", "message": "Already in use"}])

    repo.update(conn, project_id, fields)
    return _reload(conn, actor, project_id)


def _check_dates_fit_children(conn: psycopg.Connection[Any], project_id: uuid.UUID, start: Any, end: Any) -> None:
    """New project dates must still contain every milestone and team assignment."""
    m = milestones_repo.bounds(conn, project_id)
    a = assignments_repo.bounds_for_project(conn, project_id)
    if m["first_start"] and start > m["first_start"]:
        raise _field_error("start_date", f"A milestone starts on {m['first_start']}, before the new start date")
    if m["last_due"] and end < m["last_due"]:
        raise _field_error("end_date", f"A milestone is due on {m['last_due']}, after the new end date")
    if a["first_start"] and start > a["first_start"]:
        raise _field_error("start_date", f"A team member starts on {a['first_start']}, before the new start date")
    if a["last_end"] and end < a["last_end"]:
        raise _field_error("end_date", f"A team member is assigned until {a['last_end']}, after the new end date")


def complete_project(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> ProjectOut:
    """The manager (or an admin) declares the project finished; the team is released today."""
    row = get_manageable(conn, actor, project_id)
    if row["status"] != "active":
        raise ConflictError("Only a project that has started can be completed")
    repo.set_status(conn, project_id, "completed", completed_at=dates.now())
    assignments_repo.release_project(conn, project_id, dates.today())
    return _reload(conn, actor, project_id)


def archive_project(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> ProjectOut:
    """Admin archives a project (nothing is deleted); the team is released today."""
    row = get_visible(conn, actor, project_id)
    if row["archived_at"] is None:
        repo.set_status(conn, project_id, "archived", completed_at=row["completed_at"], archived_at=dates.now())
        assignments_repo.release_project(conn, project_id, dates.today())
    return _reload(conn, actor, project_id)


def unarchive_project(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> ProjectOut:
    """Admin restores an archived project to the state it was archived from."""
    row = get_visible(conn, actor, project_id)
    if row["archived_at"] is not None:
        if repo.name_taken(conn, row["name"], exclude_id=project_id):
            raise ConflictError("Another project already uses this name; rename it first")
        restored = "completed" if row["completed_at"] else "planned"
        repo.set_status(conn, project_id, restored, completed_at=row["completed_at"])
    return _reload(conn, actor, project_id)
