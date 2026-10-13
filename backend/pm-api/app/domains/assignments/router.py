"""HTTP endpoints for who works on which milestone."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.deps import ActiveUser, DbConn, ManagerOrAdmin
from app.domains.assignments import service
from app.domains.assignments.schemas import AssigneeAdd, AssigneeDates, AssigneeList, AssigneeOut

router = APIRouter(tags=["team"])


@router.get("/projects/{project_id}/team", response_model=AssigneeList)
def list_project_team(
    project_id: uuid.UUID, actor: ActiveUser, conn: DbConn, include_archived: bool = False
) -> AssigneeList:
    """Everyone working on any milestone of the project, with hours worked so far (labor cost for managers and admins)."""
    return service.list_project_team(conn, actor, project_id, include_archived=include_archived)


@router.get("/projects/{project_id}/milestones/{milestone_id}/team", response_model=AssigneeList)
def list_milestone_team(
    project_id: uuid.UUID, milestone_id: uuid.UUID, actor: ActiveUser, conn: DbConn, include_archived: bool = False
) -> AssigneeList:
    """People on one milestone. Only admins can include archived rows."""
    return service.list_milestone_team(conn, actor, project_id, milestone_id, include_archived=include_archived)


@router.post(
    "/projects/{project_id}/milestones/{milestone_id}/team", response_model=AssigneeOut, status_code=status.HTTP_201_CREATED
)
def add_assignee(
    project_id: uuid.UUID, milestone_id: uuid.UUID, payload: AssigneeAdd, actor: ManagerOrAdmin, conn: DbConn
) -> AssigneeOut:
    """Put an employee on the milestone. One person works one milestone per day, so overlapping dates are refused."""
    return service.add_assignee(conn, actor, project_id, milestone_id, payload)


@router.patch("/projects/{project_id}/milestones/{milestone_id}/team/{user_id}", response_model=AssigneeOut)
def update_assignee(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: AssigneeDates,
    actor: ManagerOrAdmin,
    conn: DbConn,
) -> AssigneeOut:
    """Change the dates a person works on this milestone."""
    return service.update_assignee(conn, actor, project_id, milestone_id, user_id, payload)


@router.post("/projects/{project_id}/milestones/{milestone_id}/team/{user_id}/archive", response_model=AssigneeOut)
def remove_assignee(
    project_id: uuid.UUID, milestone_id: uuid.UUID, user_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn
) -> AssigneeOut:
    """Take a person off the milestone: they work until today (never-started rows are archived, never deleted)."""
    return service.remove_assignee(conn, actor, project_id, milestone_id, user_id)
