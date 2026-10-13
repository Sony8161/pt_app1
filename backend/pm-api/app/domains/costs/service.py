"""Business rules for project costs. Money is only visible to admins and the project's manager."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

import psycopg

from app.core.deps import CurrentUser
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.domains.costs import repository as repo
from app.domains.costs.schemas import CostCreate, CostList, CostOut, CostUpdate
from app.domains.projects import service as projects


def _out(row: dict[str, Any]) -> CostOut:
    return CostOut.model_validate({**row, "amount": float(row["amount"])})


def _writable_project(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> dict[str, Any]:
    """Costs may still arrive after a project is completed, but not once it is archived."""
    project = projects.get_manageable(conn, actor, project_id, must_be_open=False)
    if project["archived_at"] is not None:
        raise ConflictError("This project is archived and can no longer be changed")
    return project


def list_costs(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID) -> CostList:
    """Cost lines and totals. Employees cannot see project money."""
    project = projects.get_visible(conn, actor, project_id)
    if actor.role == "employee":
        raise ForbiddenError("Costs are only visible to the project's manager and admins")
    rows = repo.list_for_project(conn, project_id)
    by_category: dict[str, float] = defaultdict(float)
    for row in rows:
        by_category[row["category"]] += float(row["amount"])
    other = sum(by_category.values())
    labor = float(project["labor_cost"])
    budget = float(project["budget_amount"])
    return CostList(
        items=[_out(r) for r in rows],
        total=len(rows),
        other_cost=round(other, 2),
        by_category={k: round(v, 2) for k, v in by_category.items()},
        labor_cost=round(labor, 2),
        total_cost=round(labor + other, 2),
        budget_amount=budget,
        budget_remaining=round(budget - labor - other, 2),
    )


def add_cost(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, payload: CostCreate) -> CostOut:
    """Record a non-labor expense."""
    _writable_project(conn, actor, project_id)
    cost_id = repo.insert(
        conn,
        project_id=project_id,
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        incurred_on=payload.incurred_on,
        created_by=actor.id,
    )
    return _out(_load(conn, project_id, cost_id))


def _load(conn: psycopg.Connection[Any], project_id: uuid.UUID, cost_id: uuid.UUID) -> dict[str, Any]:
    row = repo.get(conn, project_id, cost_id)
    if row is None:
        raise NotFoundError("Cost not found")
    return row


def update_cost(
    conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, cost_id: uuid.UUID, payload: CostUpdate
) -> CostOut:
    """Correct a cost line."""
    _writable_project(conn, actor, project_id)
    _load(conn, project_id, cost_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if value is None:
            raise ValidationError(
                "This field cannot be empty", details=[{"field": key, "message": "This field cannot be empty"}]
            )
    repo.update(conn, cost_id, fields)
    return _out(_load(conn, project_id, cost_id))


def remove_cost(conn: psycopg.Connection[Any], actor: CurrentUser, project_id: uuid.UUID, cost_id: uuid.UUID) -> None:
    """Remove a cost line (archived, not deleted)."""
    _writable_project(conn, actor, project_id)
    _load(conn, project_id, cost_id)
    repo.archive(conn, cost_id)
