"""Business rules for who works on which milestone.

Every Monday-Friday inside an assignment is one 8-hour shift, so hours and labor cost follow from the
dates. Several employees may work one milestone, but one person works only one milestone per day:
two assignments of the same person may never overlap in dates.
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
from app.domains.assignments.schemas import AssigneeAdd, AssigneeDates, AssigneeList, AssigneeOut
from app.domains.milestones import service as milestones
from app.domains.projects import service as projects
from app.domains.users import repository as users_repo


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(message, details=[{"field": field, "message": message}])


def _out(row: dict[str, Any], *, include_costs: bool) -> AssigneeOut:
    return AssigneeOut(
        assignment_id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        username=row["username"],
        email=row["email"],
        job_title=row["job_title"],
        milestone_id=row["milestone_id"],
        milestone_name=row["milestone_name"],
        project_id=row["project_id"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        daily_hours=dates.DAILY_HOURS,
        days_worked=int(row["days_worked"]),
        hours_worked=float(row["hours_worked"]),
        labor_cost=round(float(row["labor_cost"]), 2) if include_costs else None,
        archived_at=row["archived_at"],
    )


def _to_list(rows: list[dict[str, Any]], actor: CurrentUser) -> AssigneeList:
    include_costs = actor.role != "employee"
    items = [_out(r, include_costs=include_costs) for r in rows]
    return AssigneeList(
        items=items,
        total=len(items),
        hours_worked=round(sum(i.hours_worked for i in items), 2),
        labor_cost=round(sum(i.labor_cost or 0 for i in items), 2) if include_costs else None,
    )


def list_milestone_team(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID, *, include_archived: bool
) -> AssigneeList:
    """People on one milestone. Labor cost is hidden from employees; archived rows are admin-only."""
    projects.get_visible(conn, actor, project_id)
    milestones.load(conn, actor, project_id, milestone_id)
    rows = repo.list_for_milestone(conn, milestone_id, dates.today(), include_archived=include_archived and actor.is_admin)
    return _to_list(rows, actor)


def list_project_team(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, *, include_archived: bool
) -> AssigneeList:
    """Everyone working on any milestone of a project (the project's team)."""
    projects.get_visible(conn, actor, project_id)
    rows = repo.list_for_project(conn, project_id, dates.today(), include_archived=include_archived and actor.is_admin)
    return _to_list(rows, actor)


def _member(
    conn: psycopg.Connection[Any], actor: CurrentUser, milestone_id: uuid.UUID, user_id: uuid.UUID, *, archived: bool = False
) -> AssigneeOut:
    for row in repo.list_for_milestone(conn, milestone_id, dates.today(), include_archived=True):
        if row["user_id"] == user_id and (archived or row["archived_at"] is None):
            return _out(row, include_costs=actor.role != "employee")
    raise NotFoundError("That person is not on this milestone")


def _check_range(milestone: dict[str, Any], start: dt.date, end: dt.date) -> None:
    if end < start:
        raise _field_error("end_date", "The end date must be on or after the start date")
    if start < milestone["start_date"] or end > milestone["due_date"]:
        raise _field_error(
            "start_date", f"Dates must be inside the milestone: {milestone['start_date']} to {milestone['due_date']}"
        )


def _check_no_overlap(
    conn: psycopg.Connection[Any], user: dict[str, Any], start: dt.date, end: dt.date, exclude: uuid.UUID | None = None
) -> None:
    clash = repo.find_overlap(conn, user["id"], start, end, exclude_id=exclude)
    if clash:
        raise ConflictError(
            f"{user['name']} is already on milestone '{clash['milestone_name']}' of '{clash['project_name']}' from "
            f"{clash['start_date']} to {clash['end_date']}. A person works one milestone per day, "
            "so choose dates outside that range.",
            code="assignment_overlap",
            details=[{"field": "start_date", "message": f"Overlaps '{clash['milestone_name']}'"}],
        )


def add_assignee(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID, payload: AssigneeAdd
) -> AssigneeOut:
    """Put an employee on a milestone."""
    projects.get_manageable(conn, actor, project_id)
    milestone = milestones.load_live(conn, actor, project_id, milestone_id)
    user = users_repo.get_by_id(conn, payload.user_id)
    if user is None or user["archived_at"] is not None:
        raise _field_error("user_id", "That person does not exist or is archived")
    if user["role"] != "employee":
        raise _field_error("user_id", "Only employees can be put on a milestone")
    if repo.get_active(conn, milestone_id, user["id"]):
        raise ConflictError("That person is already on this milestone. Change their dates instead.")

    start = payload.start_date or max(milestone["start_date"], dates.today())
    end = payload.end_date or milestone["due_date"]
    if start > end and payload.start_date is None:
        raise _field_error("start_date", "The milestone's due date has passed; extend the milestone first")
    _check_range(milestone, start, end)

    repo.lock_user(conn, user["id"])
    _check_no_overlap(conn, user, start, end)
    repo.insert(conn, milestone_id=milestone_id, user_id=user["id"], start_date=start, end_date=end, assigned_by=actor.id)
    return _member(conn, actor, milestone_id, user["id"])


def update_assignee(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: AssigneeDates,
) -> AssigneeOut:
    """Change the dates an employee works on the milestone."""
    projects.get_manageable(conn, actor, project_id)
    milestone = milestones.load_live(conn, actor, project_id, milestone_id)
    current = repo.get_active(conn, milestone_id, user_id)
    if current is None:
        raise NotFoundError("That person is not on this milestone")
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is None:
            raise _field_error(key, "This field cannot be empty")
    start = fields.get("start_date", current["start_date"])
    end = fields.get("end_date", current["end_date"])
    _check_range(milestone, start, end)

    user = users_repo.get_by_id(conn, user_id)
    if user is None:  # pragma: no cover - FK guarantees it
        raise NotFoundError("User not found")
    repo.lock_user(conn, user_id)
    _check_no_overlap(conn, user, start, end, exclude=current["id"])
    repo.update_dates(conn, current["id"], start, end)
    return _member(conn, actor, milestone_id, user_id)


def remove_assignee(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID, user_id: uuid.UUID
) -> AssigneeOut:
    """Take a person off a milestone. They work until today; if they never started the row is archived."""
    projects.get_manageable(conn, actor, project_id)
    milestones.load_live(conn, actor, project_id, milestone_id)
    current = repo.get_active(conn, milestone_id, user_id)
    if current is None:
        raise NotFoundError("That person is not on this milestone")
    repo.end_assignment(conn, current["id"], dates.today())
    return _member(conn, actor, milestone_id, user_id, archived=True)
