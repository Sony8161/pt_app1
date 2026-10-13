"""HTTP endpoints for deliverables, nested under a milestone."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.deps import ActiveUser, DbConn, ManagerOrAdmin
from app.domains.deliverables import service
from app.domains.deliverables.schemas import DeliverableCreate, DeliverableList, DeliverableOut, DeliverableUpdate

router = APIRouter(prefix="/projects/{project_id}/milestones/{milestone_id}/deliverables", tags=["deliverables"])


@router.get("", response_model=DeliverableList)
def list_deliverables(
    project_id: uuid.UUID, milestone_id: uuid.UUID, actor: ActiveUser, conn: DbConn, include_archived: bool = False
) -> DeliverableList:
    """The milestone's checklist and whether it is ready to be completed. Only admins can include archived items."""
    return service.list_deliverables(conn, actor, project_id, milestone_id, include_archived=include_archived)


@router.post("", response_model=DeliverableOut, status_code=status.HTTP_201_CREATED)
def add_deliverable(
    project_id: uuid.UUID, milestone_id: uuid.UUID, payload: DeliverableCreate, actor: ManagerOrAdmin, conn: DbConn
) -> DeliverableOut:
    """Add something the milestone must produce."""
    return service.add_deliverable(conn, actor, project_id, milestone_id, payload)


@router.patch("/{deliverable_id}", response_model=DeliverableOut)
def update_deliverable(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    payload: DeliverableUpdate,
    actor: ManagerOrAdmin,
    conn: DbConn,
) -> DeliverableOut:
    """Rename a deliverable or tick it off after review (`done`: true)."""
    return service.update_deliverable(conn, actor, project_id, milestone_id, deliverable_id, payload)


@router.post("/{deliverable_id}/archive", response_model=DeliverableOut)
def archive_deliverable(
    project_id: uuid.UUID, milestone_id: uuid.UUID, deliverable_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn
) -> DeliverableOut:
    """Take a deliverable off the checklist. It is archived, never deleted, and only admins can see it."""
    return service.archive_deliverable(conn, actor, project_id, milestone_id, deliverable_id)
