"""SQL access for ``milestones``."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg
from psycopg import sql

_EDITABLE = frozenset({"name", "description", "start_date", "due_date", "allocated_hours", "status", "completed_at"})


def list_for_project(conn: psycopg.Connection[Any], project_id: uuid.UUID, today: dt.date) -> list[dict[str, Any]]:
    """Live milestones in timeline order, each with the hours logged against it."""
    return conn.execute(
        """
        SELECT m.*, COALESCE(t.hours, 0) AS hours_logged,
               (m.status <> 'done' AND m.due_date < %s) AS is_overdue
        FROM milestones m
        LEFT JOIN LATERAL (
            SELECT sum(hours) AS hours FROM time_entries WHERE milestone_id = m.id AND archived_at IS NULL
        ) t ON true
        WHERE m.project_id = %s AND m.archived_at IS NULL
        ORDER BY m.start_date, m.due_date, lower(m.name)
        """,
        (today, project_id),
    ).fetchall()


def get(
    conn: psycopg.Connection[Any], project_id: uuid.UUID, milestone_id: uuid.UUID, today: dt.date
) -> dict[str, Any] | None:
    """One live milestone of a project."""
    return conn.execute(
        """
        SELECT m.*, COALESCE(t.hours, 0) AS hours_logged,
               (m.status <> 'done' AND m.due_date < %s) AS is_overdue
        FROM milestones m
        LEFT JOIN LATERAL (
            SELECT sum(hours) AS hours FROM time_entries WHERE milestone_id = m.id AND archived_at IS NULL
        ) t ON true
        WHERE m.id = %s AND m.project_id = %s AND m.archived_at IS NULL
        """,
        (today, milestone_id, project_id),
    ).fetchone()


def name_taken(
    conn: psycopg.Connection[Any], project_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None
) -> bool:
    """True when the project already has a live milestone with this name (case-insensitive)."""
    return (
        conn.execute(
            "SELECT 1 FROM milestones WHERE project_id = %s AND lower(name) = lower(%s) AND archived_at IS NULL "
            "AND (%s::uuid IS NULL OR id <> %s)",
            (project_id, name, exclude_id, exclude_id),
        ).fetchone()
        is not None
    )


def hours_total(conn: psycopg.Connection[Any], project_id: uuid.UUID, *, exclude_id: uuid.UUID | None = None) -> float:
    """Sum of allocated hours over a project's live milestones."""
    row = conn.execute(
        "SELECT COALESCE(sum(allocated_hours), 0) AS n FROM milestones WHERE project_id = %s AND archived_at IS NULL "
        "AND (%s::uuid IS NULL OR id <> %s)",
        (project_id, exclude_id, exclude_id),
    ).fetchone()
    return float(row["n"]) if row else 0.0


def bounds(conn: psycopg.Connection[Any], project_id: uuid.UUID) -> dict[str, Any]:
    """Earliest start and latest due date among a project's live milestones."""
    row = conn.execute(
        "SELECT min(start_date) AS first_start, max(due_date) AS last_due FROM milestones "
        "WHERE project_id = %s AND archived_at IS NULL",
        (project_id,),
    ).fetchone()
    return row or {"first_start": None, "last_due": None}


def insert(
    conn: psycopg.Connection[Any],
    *,
    project_id: uuid.UUID,
    name: str,
    description: str,
    start_date: dt.date,
    due_date: dt.date,
    allocated_hours: float,
) -> uuid.UUID:
    """Create a milestone and return its id."""
    row = conn.execute(
        """
        INSERT INTO milestones (project_id, name, description, start_date, due_date, allocated_hours)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (project_id, name, description, start_date, due_date, allocated_hours),
    ).fetchone()
    if row is None:  # pragma: no cover - RETURNING always yields the inserted row
        raise RuntimeError("INSERT INTO milestones returned no row")
    return row["id"]


def update(conn: psycopg.Connection[Any], milestone_id: uuid.UUID, fields: dict[str, Any]) -> None:
    """Update editable columns (anything else is ignored)."""
    clean = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not clean:
        return
    sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in clean)
    conn.execute(sql.SQL("UPDATE milestones SET {sets} WHERE id = %s").format(sets=sets), (*clean.values(), milestone_id))


def archive(conn: psycopg.Connection[Any], milestone_id: uuid.UUID) -> None:
    """Remove a milestone from the plan (the row is kept)."""
    conn.execute("UPDATE milestones SET archived_at = now() WHERE id = %s", (milestone_id,))
