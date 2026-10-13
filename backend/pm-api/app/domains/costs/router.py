"""HTTP endpoints for project costs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.deps import ActiveUser, DbConn, ManagerOrAdmin
from app.domains.costs import service
from app.domains.costs.schemas import CostCreate, CostList, CostOut, CostUpdate

router = APIRouter(prefix="/projects/{project_id}/costs", tags=["costs"])


@router.get("", response_model=CostList)
def list_costs(project_id: uuid.UUID, actor: ActiveUser, conn: DbConn, include_archived: bool = False) -> CostList:
    """Non-labor costs with totals against the budget (not available to employees; only admins can include archived lines)."""
    return service.list_costs(conn, actor, project_id, include_archived=include_archived)


@router.post("", response_model=CostOut, status_code=status.HTTP_201_CREATED)
def add_cost(project_id: uuid.UUID, payload: CostCreate, actor: ManagerOrAdmin, conn: DbConn) -> CostOut:
    """Record technology, license, vendor, travel or other costs."""
    return service.add_cost(conn, actor, project_id, payload)


@router.patch("/{cost_id}", response_model=CostOut)
def update_cost(project_id: uuid.UUID, cost_id: uuid.UUID, payload: CostUpdate, actor: ManagerOrAdmin, conn: DbConn) -> CostOut:
    """Correct a cost line."""
    return service.update_cost(conn, actor, project_id, cost_id, payload)


@router.post("/{cost_id}/archive", response_model=CostOut)
def archive_cost(project_id: uuid.UUID, cost_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn) -> CostOut:
    """Take a cost line out of the totals. It is archived, never deleted, and only admins can see it."""
    return service.archive_cost(conn, actor, project_id, cost_id)
