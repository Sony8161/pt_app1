"""HTTP endpoints for milestones, nested under a project."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.core.deps import ActiveUser, DbConn, ManagerOrAdmin
from app.domains.milestones import service
from app.domains.milestones.schemas import MilestoneCreate, MilestoneList, MilestoneOut, MilestoneUpdate

router = APIRouter(prefix="/projects/{project_id}/milestones", tags=["milestones"])


@router.get("", response_model=MilestoneList)
def list_milestones(project_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> MilestoneList:
    """Milestones of a project, in timeline order."""
    return service.list_milestones(conn, actor, project_id)


@router.post("", response_model=MilestoneOut, status_code=status.HTTP_201_CREATED)
def create_milestone(project_id: uuid.UUID, payload: MilestoneCreate, actor: ManagerOrAdmin, conn: DbConn) -> MilestoneOut:
    """Add a milestone. Its dates must sit inside the project's dates."""
    return service.create_milestone(conn, actor, project_id, payload)


@router.get("/{milestone_id}", response_model=MilestoneOut)
def get_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> MilestoneOut:
    """One milestone."""
    return service.get_milestone(conn, actor, project_id, milestone_id)


@router.patch("/{milestone_id}", response_model=MilestoneOut)
def update_milestone(
    project_id: uuid.UUID, milestone_id: uuid.UUID, payload: MilestoneUpdate, actor: ManagerOrAdmin, conn: DbConn
) -> MilestoneOut:
    """Edit a milestone or set its status (pending, in_progress, done)."""
    return service.update_milestone(conn, actor, project_id, milestone_id, payload)


@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn) -> Response:
    """Remove a milestone from the plan (archived, not deleted)."""
    service.archive_milestone(conn, actor, project_id, milestone_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
