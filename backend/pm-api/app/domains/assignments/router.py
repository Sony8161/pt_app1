"""HTTP endpoints for project teams."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.core.deps import ActiveUser, DbConn, ManagerOrAdmin
from app.domains.assignments import service
from app.domains.assignments.schemas import TeamList, TeamMemberAdd, TeamMemberDates, TeamMemberOut

router = APIRouter(prefix="/projects/{project_id}/team", tags=["team"])


@router.get("", response_model=TeamList)
def list_team(project_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> TeamList:
    """People on the project, with hours logged (and labor cost for managers and admins)."""
    return service.list_team(conn, actor, project_id)


@router.post("", response_model=TeamMemberOut, status_code=status.HTTP_201_CREATED)
def add_member(project_id: uuid.UUID, payload: TeamMemberAdd, actor: ManagerOrAdmin, conn: DbConn) -> TeamMemberOut:
    """Put an employee on the team. They give this project their full day for the dates chosen."""
    return service.add_member(conn, actor, project_id, payload)


@router.patch("/{user_id}", response_model=TeamMemberOut)
def update_member(
    project_id: uuid.UUID, user_id: uuid.UUID, payload: TeamMemberDates, actor: ManagerOrAdmin, conn: DbConn
) -> TeamMemberOut:
    """Change the dates a person works on this project."""
    return service.update_member(conn, actor, project_id, user_id, payload)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(project_id: uuid.UUID, user_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn) -> Response:
    """Take a person off the team. Their logged time stays on record."""
    service.remove_member(conn, actor, project_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
