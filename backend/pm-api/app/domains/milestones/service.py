"""Business rules for milestones. Only the project's manager (or an admin) changes them."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg

from app.core import dates
from app.core.deps import CurrentUser
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domains.milestones import repository as repo
from app.domains.milestones.schemas import MilestoneCreate, MilestoneList, MilestoneOut, MilestoneUpdate
from app.domains.projects import service as projects


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(message, details=[{"field": field, "message": message}])


def _out(row: dict[str, Any]) -> MilestoneOut:
    return MilestoneOut.model_validate({**row, "allocated_hours": float(row["allocated_hours"]),
                                        "hours_logged": float(row["hours_logged"])})


def _check_inside_project(project: dict[str, Any], start: Any, due: Any) -> None:
    if start < project["start_date"] or due > project["end_date"]:
        raise _field_error(
            "due_date",
            f"Milestone dates must be inside the project: {project['start_date']} to {project['end_date']}",
        )


def _check_hours(conn: psycopg.Connection[Any], project: dict[str, Any], hours: float, exclude: uuid.UUID | None) -> None:
    planned = repo.hours_total(conn, project["id"], exclude_id=exclude) + hours
    allowed = float(project["allocated_hours"])
    if planned > allowed:
        raise _field_error(
            "allocated_hours",
            f"The milestones would plan {planned:g} hours but the project only has {allowed:g}. "
            "Raise the project's allocated hours first.",
        )


def list_milestones(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> MilestoneList:
    """Milestones of a project you can see."""
    projects.get_visible(conn, actor, project_id)
    rows = repo.list_for_project(conn, project_id, dates.today())
    return MilestoneList(
        items=[_out(r) for r in rows], total=len(rows), planned_hours=sum(float(r["allocated_hours"]) for r in rows)
    )


def get_milestone(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> MilestoneOut:
    """One milestone of a project you can see."""
    projects.get_visible(conn, actor, project_id)
    return _out(_load(conn, project_id, milestone_id))


def _load(conn: psycopg.Connection[Any], project_id: uuid.UUID, milestone_id: uuid.UUID) -> dict[str, Any]:
    row = repo.get(conn, project_id, milestone_id, dates.today())
    if row is None:
        raise NotFoundError("Milestone not found")
    return row


def create_milestone(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, payload: MilestoneCreate
) -> MilestoneOut:
    """Add a milestone to the plan."""
    project = projects.get_manageable(conn, actor, project_id)
    _check_inside_project(project, payload.start_date, payload.due_date)
    if repo.name_taken(conn, project_id, payload.name):
        raise ConflictError("This project already has a milestone with that name",
                            details=[{"field": "name", "message": "Already in use"}])
    _check_hours(conn, project, payload.allocated_hours, None)
    milestone_id = repo.insert(
        conn,
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        start_date=payload.start_date,
        due_date=payload.due_date,
        allocated_hours=payload.allocated_hours,
    )
    return _out(_load(conn, project_id, milestone_id))


def update_milestone(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
) -> MilestoneOut:
    """Edit a milestone, or mark it ``done`` when the manager says it has been reached."""
    project = projects.get_manageable(conn, actor, project_id)
    current = _load(conn, project_id, milestone_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is None:
            raise _field_error(key, "This field cannot be empty")

    start = fields.get("start_date", current["start_date"])
    due = fields.get("due_date", current["due_date"])
    if due < start:
        raise _field_error("due_date", "The due date must be on or after the start date")
    if "start_date" in fields or "due_date" in fields:
        _check_inside_project(project, start, due)
    if "name" in fields and fields["name"].lower() != current["name"].lower() and repo.name_taken(
        conn, project_id, fields["name"], exclude_id=milestone_id
    ):
        raise ConflictError("This project already has a milestone with that name",
                            details=[{"field": "name", "message": "Already in use"}])
    if "allocated_hours" in fields:
        _check_hours(conn, project, fields["allocated_hours"], milestone_id)

    if "status" in fields:
        if fields["status"] == "done" and current["status"] != "done":
            fields["completed_at"] = dates.now()
        elif fields["status"] != "done":
            fields["completed_at"] = None

    repo.update(conn, milestone_id, fields)
    return _out(_load(conn, project_id, milestone_id))


def archive_milestone(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> None:
    """Take a milestone out of the plan (logged time keeps its link)."""
    projects.get_manageable(conn, actor, project_id)
    _load(conn, project_id, milestone_id)
    repo.archive(conn, milestone_id)
