"""SQL access for ``project_costs`` (non-labor spend)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg
from psycopg import sql

_EDITABLE = frozenset({"category", "description", "amount", "incurred_on"})


def list_for_project(conn: psycopg.Connection[Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Live cost lines, newest first."""
    return conn.execute(
        "SELECT * FROM project_costs WHERE project_id = %s AND archived_at IS NULL "
        "ORDER BY incurred_on DESC, created_at DESC",
        (project_id,),
    ).fetchall()


def get(conn: psycopg.Connection[Any], project_id: uuid.UUID, cost_id: uuid.UUID) -> dict[str, Any] | None:
    """One live cost line of a project."""
    return conn.execute(
        "SELECT * FROM project_costs WHERE id = %s AND project_id = %s AND archived_at IS NULL", (cost_id, project_id)
    ).fetchone()


def insert(
    conn: psycopg.Connection[Any],
    *,
    project_id: uuid.UUID,
    category: str,
    description: str,
    amount: float,
    incurred_on: dt.date,
    created_by: uuid.UUID,
) -> uuid.UUID:
    """Record a cost and return its id."""
    row = conn.execute(
        """
        INSERT INTO project_costs (project_id, category, description, amount, incurred_on, created_by)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (project_id, category, description, amount, incurred_on, created_by),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO project_costs returned no row")
    return row["id"]


def update(conn: psycopg.Connection[Any], cost_id: uuid.UUID, fields: dict[str, Any]) -> None:
    """Update editable columns (anything else is ignored)."""
    clean = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not clean:
        return
    sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in clean)
    conn.execute(sql.SQL("UPDATE project_costs SET {sets} WHERE id = %s").format(sets=sets), (*clean.values(), cost_id))


def archive(conn: psycopg.Connection[Any], cost_id: uuid.UUID) -> None:
    """Remove a cost line (archived, not deleted)."""
    conn.execute("UPDATE project_costs SET archived_at = now() WHERE id = %s", (cost_id,))
