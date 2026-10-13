"""HTTP endpoints for milestones, nested under a project."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.deps import ActiveUser, DbConn, ManagerOrAdmin
from app.domains.milestones import service
from app.domains.milestones.schemas import (
    MilestoneComplete,
    MilestoneCreate,
    MilestoneList,
    MilestoneOut,
    MilestoneUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/milestones", tags=["milestones"])


@router.get("", response_model=MilestoneList)
def list_milestones(
    project_id: uuid.UUID, actor: ActiveUser, conn: DbConn, include_archived: bool = False
) -> MilestoneList:
    """Milestones of a project, in timeline order. Completed and cancelled ones are archived; only admins can include them."""
    return service.list_milestones(conn, actor, project_id, include_archived=include_archived)


@router.post("", response_model=MilestoneOut, status_code=status.HTTP_201_CREATED)
def create_milestone(project_id: uuid.UUID, payload: MilestoneCreate, actor: ManagerOrAdmin, conn: DbConn) -> MilestoneOut:
    """Add a milestone. Its dates, hours and budget must fit inside the project's."""
    return service.create_milestone(conn, actor, project_id, payload)


@router.get("/{milestone_id}", response_model=MilestoneOut)
def get_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> MilestoneOut:
    """One milestone (archived ones are only visible to admins)."""
    return service.get_milestone(conn, actor, project_id, milestone_id)


@router.patch("/{milestone_id}", response_model=MilestoneOut)
def update_milestone(
    project_id: uuid.UUID, milestone_id: uuid.UUID, payload: MilestoneUpdate, actor: ManagerOrAdmin, conn: DbConn
) -> MilestoneOut:
    """Edit a milestone's plan or move it between pending and in_progress."""
    return service.update_milestone(conn, actor, project_id, milestone_id, payload)


@router.post("/{milestone_id}/complete", response_model=MilestoneOut)
def complete_milestone(
    project_id: uuid.UUID, milestone_id: uuid.UUID, payload: MilestoneComplete, actor: ManagerOrAdmin, conn: DbConn
) -> MilestoneOut:
    """Sign off the milestone after reviewing its deliverables (all must be ticked). It then moves to the archive."""
    return service.complete_milestone(conn, actor, project_id, milestone_id, payload)


@router.post("/{milestone_id}/archive", response_model=MilestoneOut)
def archive_milestone(project_id: uuid.UUID, milestone_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn) -> MilestoneOut:
    """Cancel a milestone without completing it. It is archived, never deleted, and only admins can see it."""
    return service.archive_milestone(conn, actor, project_id, milestone_id)
