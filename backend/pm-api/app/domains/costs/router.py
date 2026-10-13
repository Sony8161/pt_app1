"""HTTP endpoints for project costs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.core.deps import ActiveUser, DbConn, ManagerOrAdmin
from app.domains.costs import service
from app.domains.costs.schemas import CostCreate, CostList, CostOut, CostUpdate

router = APIRouter(prefix="/projects/{project_id}/costs", tags=["costs"])


@router.get("", response_model=CostList)
def list_costs(project_id: uuid.UUID, actor: ActiveUser, conn: DbConn) -> CostList:
    """Non-labor costs with totals against the budget (not available to employees)."""
    return service.list_costs(conn, actor, project_id)


@router.post("", response_model=CostOut, status_code=status.HTTP_201_CREATED)
def add_cost(project_id: uuid.UUID, payload: CostCreate, actor: ManagerOrAdmin, conn: DbConn) -> CostOut:
    """Record technology, license, vendor, travel or other costs."""
    return service.add_cost(conn, actor, project_id, payload)


@router.patch("/{cost_id}", response_model=CostOut)
def update_cost(project_id: uuid.UUID, cost_id: uuid.UUID, payload: CostUpdate, actor: ManagerOrAdmin, conn: DbConn) -> CostOut:
    """Correct a cost line."""
    return service.update_cost(conn, actor, project_id, cost_id, payload)


@router.delete("/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_cost(project_id: uuid.UUID, cost_id: uuid.UUID, actor: ManagerOrAdmin, conn: DbConn) -> Response:
    """Remove a cost line (archived, not deleted)."""
    service.remove_cost(conn, actor, project_id, cost_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
