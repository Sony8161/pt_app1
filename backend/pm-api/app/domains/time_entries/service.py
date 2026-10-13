"""Business rules for time tracking.

Hours can only be logged by (or for) a person who is on the project team on that date, on a
project that is running, never for a future day, and never beyond 8 hours per person per day.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

import psycopg

from app.core import dates
from app.core.deps import CurrentUser
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.domains.assignments import repository as assignments_repo
from app.domains.milestones import repository as milestones_repo
from app.domains.projects import service as projects
from app.domains.time_entries import repository as repo
from app.domains.time_entries.schemas import (
    DayTotal,
    MyTimeList,
    TimeEntryCreate,
    TimeEntryList,
    TimeEntryOut,
)
from app.domains.users import repository as users_repo


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(message, details=[{"field": field, "message": message}])


def _out(row: dict[str, Any], *, include_costs: bool) -> TimeEntryOut:
    return TimeEntryOut(
        id=row["id"],
        project_id=row["project_id"],
        project_name=row["project_name"],
        user_id=row["user_id"],
        user_name=row["user_name"],
        milestone_id=row["milestone_id"],
        work_date=row["work_date"],
        hours=float(row["hours"]),
        notes=row["notes"],
        labor_cost=round(float(row["labor_cost"]), 2) if include_costs else None,
        created_at=row["created_at"],
    )


def log_time(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, payload: TimeEntryCreate
) -> TimeEntryOut:
    """Log hours on a project."""
    project = projects.get_visible(conn, actor, project_id)
    is_manager_of_project = actor.is_admin or project["manager_id"] == actor.id
    target_id = payload.user_id or actor.id
    if target_id != actor.id and not is_manager_of_project:
        raise ForbiddenError("You can only log your own time")

    if project["status"] == "planned":
        raise ConflictError("This project has not started yet")
    if project["status"] != "active":
        raise ConflictError(f"This project is {project['status']}; time can no longer be logged")
    if payload.work_date > dates.today():
        raise _field_error("work_date", "Time cannot be logged for a future date")

    person = users_repo.get_by_id(conn, target_id)
    if person is None or person["archived_at"] is not None:
        raise _field_error("user_id", "That person does not exist or is archived")

    if assignments_repo.covering(conn, project_id, target_id, payload.work_date) is None:
        raise ConflictError(
            f"{person['name']} is not on this project's team on {payload.work_date}",
            code="not_assigned",
            details=[{"field": "work_date", "message": "Outside the person's assignment dates"}],
        )

    if payload.milestone_id is not None and milestones_repo.get(
        conn, project_id, payload.milestone_id, dates.today()
    ) is None:
        raise _field_error("milestone_id", "That milestone does not belong to this project")

    assignments_repo.lock_user(conn, target_id)
    already = repo.day_total(conn, target_id, payload.work_date)
    if already + payload.hours > dates.DAILY_HOURS + 1e-9:
        left = max(dates.DAILY_HOURS - already, 0)
        raise ConflictError(
            f"{person['name']} already has {already:g} h logged on {payload.work_date}; "
            f"only {left:g} h are left of the {dates.DAILY_HOURS}-hour day.",
            code="daily_limit",
            details=[{"field": "hours", "message": f"At most {left:g} h"}],
        )

    entry_id = repo.insert(
        conn,
        project_id=project_id,
        user_id=target_id,
        milestone_id=payload.milestone_id,
        work_date=payload.work_date,
        hours=payload.hours,
        notes=payload.notes,
    )
    row = repo.get(conn, project_id, entry_id)
    if row is None:  # pragma: no cover - just inserted
        raise NotFoundError("Time entry not found")
    return _out(row, include_costs=actor.role != "employee")


def list_project_time(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    project_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    start: dt.date | None,
    end: dt.date | None,
) -> TimeEntryList:
    """Time logged on a project. Employees only ever see their own entries."""
    projects.get_visible(conn, actor, project_id)
    if actor.role == "employee":
        user_id = actor.id
    rows = repo.list_for_project(conn, project_id, user_id=user_id, start=start, end=end)
    include_costs = actor.role != "employee"
    items = [_out(r, include_costs=include_costs) for r in rows]
    return TimeEntryList(items=items, total=len(items), total_hours=round(sum(i.hours for i in items), 2))


def delete_entry(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    """Remove an entry (archived). Employees may remove their own while the project is running."""
    project = projects.get_visible(conn, actor, project_id)
    row = repo.get(conn, project_id, entry_id)
    if row is None:
        raise NotFoundError("Time entry not found")
    if actor.is_admin or project["manager_id"] == actor.id:
        repo.archive(conn, entry_id)
        return
    if row["user_id"] != actor.id:
        raise ForbiddenError("You can only remove your own time entries")
    if project["status"] != "active":
        raise ConflictError(f"This project is {project['status']}; time entries can no longer be removed")
    repo.archive(conn, entry_id)


def my_time(conn: psycopg.Connection[Any], actor: CurrentUser, start: dt.date | None, end: dt.date | None) -> MyTimeList:
    """Your own entries across projects (default: the last 14 days) with a per-day tally."""
    end = end or dates.today()
    start = start or end - dt.timedelta(days=13)
    if end < start:
        raise _field_error("to", "The 'to' date must not be before the 'from' date")
    rows = repo.list_for_user(conn, actor.id, start, end)
    items = [_out(r, include_costs=True) for r in rows]
    per_day: dict[dt.date, float] = defaultdict(float)
    for item in items:
        per_day[item.work_date] += item.hours
    daily = [
        DayTotal(date=d, hours=round(h, 2), remaining=round(max(dates.DAILY_HOURS - h, 0), 2))
        for d, h in sorted(per_day.items(), reverse=True)
    ]
    return MyTimeList(
        items=items, total=len(items), total_hours=round(sum(per_day.values()), 2), daily_totals=daily
    )
