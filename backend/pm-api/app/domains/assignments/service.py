"""Business rules for project teams.

An employee gives a project their full 8-hour day. They may belong to several projects
over time, but two assignments of the same person may never overlap in dates.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg

from app.core import dates
from app.core.deps import CurrentUser
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domains.assignments import repository as repo
from app.domains.assignments.schemas import TeamList, TeamMemberAdd, TeamMemberDates, TeamMemberOut
from app.domains.projects import service as projects
from app.domains.time_entries import repository as time_repo
from app.domains.users import repository as users_repo


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(message, details=[{"field": field, "message": message}])


def _out(row: dict[str, Any], *, include_costs: bool) -> TeamMemberOut:
    return TeamMemberOut(
        assignment_id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        username=row["username"],
        email=row["email"],
        job_title=row["job_title"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        daily_hours=dates.DAILY_HOURS,
        hours_logged=float(row["hours_logged"]),
        labor_cost=round(float(row["labor_cost"]), 2) if include_costs else None,
    )


def _member(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, user_id: uuid.UUID) -> TeamMemberOut:
    for row in repo.list_for_project(conn, project_id):
        if row["user_id"] == user_id:
            return _out(row, include_costs=actor.role != "employee")
    raise NotFoundError("That person is not on this project's team")


def list_team(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> TeamList:
    """Team of a project you can see (labor cost is hidden from employees)."""
    projects.get_visible(conn, actor, project_id)
    rows = repo.list_for_project(conn, project_id)
    include_costs = actor.role != "employee"
    return TeamList(items=[_out(r, include_costs=include_costs) for r in rows], total=len(rows))


def _check_range(project: dict[str, Any], start: dt.date, end: dt.date) -> None:
    if end < start:
        raise _field_error("end_date", "The end date must be on or after the start date")
    if start < project["start_date"] or end > project["end_date"]:
        raise _field_error(
            "start_date", f"Dates must be inside the project: {project['start_date']} to {project['end_date']}"
        )


def _check_no_overlap(
    conn: psycopg.Connection[Any], user: dict[str, Any], start: dt.date, end: dt.date, exclude: uuid.UUID | None = None
) -> None:
    clash = repo.find_overlap(conn, user["id"], start, end, exclude_id=exclude)
    if clash:
        raise ConflictError(
            f"{user['name']} is already on '{clash['project_name']}' from {clash['start_date']} to "
            f"{clash['end_date']}. A person gives one project their full day, so choose dates outside that range.",
            code="assignment_overlap",
            details=[{"field": "start_date", "message": f"Overlaps '{clash['project_name']}'"}],
        )


def add_member(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, payload: TeamMemberAdd
) -> TeamMemberOut:
    """Put an employee on the team."""
    project = projects.get_manageable(conn, actor, project_id)
    user = users_repo.get_by_id(conn, payload.user_id)
    if user is None or user["archived_at"] is not None:
        raise _field_error("user_id", "That person does not exist or is archived")
    if user["role"] != "employee":
        raise _field_error("user_id", "Only employees can be put on a project team")
    if repo.get_active(conn, project_id, user["id"]):
        raise ConflictError("That person is already on this team. Change their dates instead.")

    default_start = max(project["start_date"], dates.today()) if project["status"] == "active" else project["start_date"]
    start = payload.start_date or default_start
    end = payload.end_date or project["end_date"]
    if start > end and payload.start_date is None:
        raise _field_error("start_date", "The project is already past its end date")
    _check_range(project, start, end)

    repo.lock_user(conn, user["id"])
    _check_no_overlap(conn, user, start, end)
    repo.insert(conn, project_id=project_id, user_id=user["id"], start_date=start, end_date=end, assigned_by=actor.id)
    return _member(conn, actor, project_id, user["id"])


def update_member(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: TeamMemberDates,
) -> TeamMemberOut:
    """Change the dates an employee works on the project."""
    project = projects.get_manageable(conn, actor, project_id)
    current = repo.get_active(conn, project_id, user_id)
    if current is None:
        raise NotFoundError("That person is not on this project's team")
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is None:
            raise _field_error(key, "This field cannot be empty")
    start = fields.get("start_date", current["start_date"])
    end = fields.get("end_date", current["end_date"])
    _check_range(project, start, end)

    logged = time_repo.date_range(conn, project_id, user_id)
    if logged["first"] and (logged["first"] < start or logged["last"] > end):
        raise ConflictError(
            f"Time is already logged from {logged['first']} to {logged['last']}; "
            "the dates must still cover it."
        )

    user = users_repo.get_by_id(conn, user_id)
    if user is None:  # pragma: no cover - FK guarantees it
        raise NotFoundError("User not found")
    repo.lock_user(conn, user_id)
    _check_no_overlap(conn, user, start, end, exclude=current["id"])
    repo.update_dates(conn, current["id"], start, end)
    return _member(conn, actor, project_id, user_id)


def remove_member(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Take a person off the team (archived; their logged time stays)."""
    projects.get_manageable(conn, actor, project_id)
    current = repo.get_active(conn, project_id, user_id)
    if current is None:
        raise NotFoundError("That person is not on this project's team")
    repo.archive(conn, current["id"])
