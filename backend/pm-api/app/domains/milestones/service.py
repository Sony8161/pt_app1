"""Business rules for milestones.

A milestone is a building block of a project. The manager (or an admin) plans it, puts employees
on it, and completes it after ticking every deliverable. Completing moves it to the archive, which
only admins can see. Cancelling a milestone (mistake) archives it too. Nothing is ever deleted.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg

from app.core import dates
from app.core.deps import CurrentUser
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.money import fits
from app.domains.assignments import repository as assignments_repo
from app.domains.deliverables import repository as deliverables_repo
from app.domains.milestones import repository as repo
from app.domains.milestones.schemas import (
    MilestoneComplete,
    MilestoneCreate,
    MilestoneList,
    MilestoneOut,
    MilestoneUpdate,
)
from app.domains.projects import service as projects


def _field_error(field: str, message: str) -> ValidationError:
    return ValidationError(message, details=[{"field": field, "message": message}])


def present(row: dict[str, Any], actor: CurrentUser) -> MilestoneOut:
    """API shape of a milestone row; money is hidden from employees."""
    money = actor.role != "employee"
    budget = float(row["budget_amount"])
    labor = float(row["labor_cost"])
    return MilestoneOut(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        description=row["description"],
        start_date=row["start_date"],
        due_date=row["due_date"],
        status=row["status"],
        is_overdue=bool(row["is_overdue"]),
        allocated_hours=float(row["allocated_hours"]),
        hours_worked=float(row["hours_worked"]),
        budget_amount=budget if money else None,
        labor_cost=round(labor, 2) if money else None,
        budget_pct=(round(100 * labor / budget, 1) if budget > 0 else None) if money else None,
        assignees=int(row["assignees"]),
        deliverables_total=int(row["deliverables_total"]),
        deliverables_done=int(row["deliverables_done"]),
        completed_at=row["completed_at"],
        review_note=row["review_note"],
        archived_at=row["archived_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def load(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> dict[str, Any]:
    """A milestone the actor may see: live ones for everybody, archived ones only for admins."""
    row = repo.get(conn, project_id, milestone_id, dates.today(), include_archived=actor.is_admin)
    if row is None:
        raise NotFoundError("Milestone not found")
    return row


def load_live(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> dict[str, Any]:
    """A milestone that can still be changed (not completed or cancelled)."""
    row = load(conn, actor, project_id, milestone_id)
    if row["archived_at"] is not None:
        raise ConflictError("This milestone is archived and can no longer be changed")
    return row


def _reload(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> MilestoneOut:
    """The milestone as it is right now, including after it moved to the archive (response to the actor's own action)."""
    row = repo.get(conn, project_id, milestone_id, dates.today(), include_archived=True)
    if row is None:  # pragma: no cover - the caller just changed this milestone
        raise NotFoundError("Milestone not found")
    return present(row, actor)


def list_milestones(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, *, include_archived: bool
) -> MilestoneList:
    """Milestones of a project you can see. Only admins can include archived (completed or cancelled) ones."""
    projects.get_visible(conn, actor, project_id)
    rows = repo.list_for_project(conn, project_id, dates.today(), include_archived=include_archived and actor.is_admin)
    items = [present(r, actor) for r in rows]
    return MilestoneList(
        items=items,
        total=len(items),
        planned_hours=round(sum(i.allocated_hours for i in items), 2),
        planned_budget=None if actor.role == "employee" else round(sum(i.budget_amount or 0 for i in items), 2),
    )


def get_milestone(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> MilestoneOut:
    """One milestone of a project you can see."""
    projects.get_visible(conn, actor, project_id)
    return present(load(conn, actor, project_id, milestone_id), actor)


def _check_inside_project(project: dict[str, Any], start: Any, due: Any) -> None:
    if start < project["start_date"] or due > project["end_date"]:
        raise _field_error(
            "due_date", f"Milestone dates must be inside the project: {project['start_date']} to {project['end_date']}"
        )


def _check_plan(
    conn: psycopg.Connection[Any], project: dict[str, Any], hours: float, budget: float, exclude: uuid.UUID | None
) -> None:
    """The milestones' planned hours and budget must fit inside the project's."""
    others = repo.plan_totals(conn, project["id"], exclude_id=exclude)
    if not fits(others["hours"] + hours, float(project["allocated_hours"])):
        raise _field_error(
            "allocated_hours",
            f"The milestones would plan {others['hours'] + hours:g} hours but the project only has "
            f"{float(project['allocated_hours']):g}. Raise the project's allocated hours first.",
        )
    if not fits(others["budget"] + budget, float(project["budget_amount"])):
        raise _field_error(
            "budget_amount",
            f"The milestones would budget {others['budget'] + budget:,.2f} but the project only has "
            f"{float(project['budget_amount']):,.2f}. Raise the project's budget first.",
        )


def create_milestone(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, payload: MilestoneCreate
) -> MilestoneOut:
    """Add a milestone to the plan."""
    project = projects.get_manageable(conn, actor, project_id)
    _check_inside_project(project, payload.start_date, payload.due_date)
    if repo.name_taken(conn, project_id, payload.name):
        raise ConflictError(
            "This project already has a milestone with that name", details=[{"field": "name", "message": "Already in use"}]
        )
    _check_plan(conn, project, payload.allocated_hours, payload.budget_amount, None)
    milestone_id = repo.insert(
        conn,
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        start_date=payload.start_date,
        due_date=payload.due_date,
        allocated_hours=payload.allocated_hours,
        budget_amount=payload.budget_amount,
    )
    return present(load(conn, actor, project_id, milestone_id), actor)


def update_milestone(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
) -> MilestoneOut:
    """Edit a milestone's plan or move it between pending and in progress."""
    project = projects.get_manageable(conn, actor, project_id)
    current = load_live(conn, actor, project_id, milestone_id)
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
        work = assignments_repo.bounds_for_milestone(conn, milestone_id)
        if work["first_start"] and (start > work["first_start"] or due < work["last_end"]):
            raise _field_error(
                "start_date",
                f"People are assigned from {work['first_start']} to {work['last_end']}; "
                "the milestone dates must still cover that.",
            )
    if "name" in fields and fields["name"].lower() != current["name"].lower() and repo.name_taken(
        conn, project_id, fields["name"], exclude_id=milestone_id
    ):
        raise ConflictError(
            "This project already has a milestone with that name", details=[{"field": "name", "message": "Already in use"}]
        )
    if "allocated_hours" in fields or "budget_amount" in fields:
        _check_plan(
            conn,
            project,
            fields.get("allocated_hours", float(current["allocated_hours"])),
            fields.get("budget_amount", float(current["budget_amount"])),
            milestone_id,
        )

    repo.update(conn, milestone_id, fields)
    return present(load(conn, actor, project_id, milestone_id), actor)


def complete_milestone(
    conn: psycopg.Connection[Any],
    actor: CurrentUser,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestoneComplete,
) -> MilestoneOut:
    """The manager signs off a milestone once every deliverable is ticked; it then moves to the archive."""
    projects.get_manageable(conn, actor, project_id)
    load_live(conn, actor, project_id, milestone_id)
    if deliverables_repo.count_live(conn, milestone_id) == 0:
        raise ConflictError(
            "Add the deliverables to review before completing this milestone", code="no_deliverables"
        )
    open_items = deliverables_repo.open_names(conn, milestone_id)
    if open_items:
        raise ConflictError(
            f"{len(open_items)} deliverable(s) are not done yet: {', '.join(open_items)}",
            code="deliverables_incomplete",
            details=[{"field": "deliverables", "message": name} for name in open_items],
        )
    repo.complete(conn, milestone_id, reviewer_id=actor.id, note=payload.review_note)
    assignments_repo.end_for_milestone(conn, milestone_id, dates.today())
    return _reload(conn, actor, project_id, milestone_id)


def archive_milestone(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, milestone_id: uuid.UUID
) -> MilestoneOut:
    """Cancel a milestone that should not be in the plan (archived, never deleted; admins can still see it)."""
    projects.get_manageable(conn, actor, project_id)
    load_live(conn, actor, project_id, milestone_id)
    repo.archive(conn, milestone_id)
    assignments_repo.end_for_milestone(conn, milestone_id, dates.today())
    return _reload(conn, actor, project_id, milestone_id)
