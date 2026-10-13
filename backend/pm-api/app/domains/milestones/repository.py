"""SQL access for ``milestones``.

A milestone is *live* while ``archived_at`` is null. Completing one archives it (admins can still
see it), and cancelling one also archives it. Project totals count live and completed milestones
but not cancelled ones: ``archived_at IS NULL OR status = 'completed'`` (written out in each query).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg
from psycopg import sql

_EDITABLE = frozenset({"name", "description", "start_date", "due_date", "allocated_hours", "budget_amount", "status"})

# The 8 in this query is core.dates.DAILY_HOURS (a test keeps them in step).
_ROW = """
    SELECT m.*,
           COALESCE(w.hours, 0)  AS hours_worked,
           COALESCE(w.labor, 0)  AS labor_cost,
           COALESCE(w.people, 0) AS assignees,
           COALESCE(d.total, 0)  AS deliverables_total,
           COALESCE(d.done, 0)   AS deliverables_done,
           (m.status <> 'completed' AND m.archived_at IS NULL AND m.due_date < %(today)s) AS is_overdue
    FROM milestones m
    LEFT JOIN LATERAL (
        SELECT sum(working_days(a.start_date, LEAST(a.end_date, %(today)s))) * 8            AS hours,
               sum(working_days(a.start_date, LEAST(a.end_date, %(today)s)) * 8 * u.salary) AS labor,
               count(DISTINCT a.user_id)                                                                AS people
        FROM milestone_assignments a JOIN users u ON u.id = a.user_id
        WHERE a.milestone_id = m.id AND a.archived_at IS NULL
    ) w ON true
    LEFT JOIN LATERAL (
        SELECT count(*) AS total, count(*) FILTER (WHERE done) AS done
        FROM deliverables WHERE milestone_id = m.id AND archived_at IS NULL
    ) d ON true
"""


def list_for_project(
    conn: psycopg.Connection[Any], project_id: uuid.UUID, today: dt.date, *, include_archived: bool = False
) -> list[dict[str, Any]]:
    """Milestones of a project in timeline order; archived ones only when asked (admins)."""
    return conn.execute(
        _ROW + " WHERE m.project_id = %(pid)s AND (%(arch)s OR m.archived_at IS NULL) "
        "ORDER BY m.start_date, m.due_date, lower(m.name)",
        {"today": today, "pid": project_id, "arch": include_archived},
    ).fetchall()


def get(
    conn: psycopg.Connection[Any],
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    today: dt.date,
    *,
    include_archived: bool = False,
) -> dict[str, Any] | None:
    """One milestone of a project; archived ones only when asked (admins)."""
    return conn.execute(
        _ROW + " WHERE m.id = %(id)s AND m.project_id = %(pid)s AND (%(arch)s OR m.archived_at IS NULL)",
        {"today": today, "id": milestone_id, "pid": project_id, "arch": include_archived},
    ).fetchone()


def name_taken(
    conn: psycopg.Connection[Any], project_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None
) -> bool:
    """True when the project already has a counted milestone with this name (case-insensitive)."""
    return (
        conn.execute(
            "SELECT 1 FROM milestones m WHERE m.project_id = %s AND lower(m.name) = lower(%s) "
            "AND (m.archived_at IS NULL OR m.status = 'completed') AND (%s::uuid IS NULL OR m.id <> %s)",
            (project_id, name, exclude_id, exclude_id),
        ).fetchone()
        is not None
    )


def plan_totals(conn: psycopg.Connection[Any], project_id: uuid.UUID, *, exclude_id: uuid.UUID | None = None) -> dict[str, float]:
    """Planned hours and budget summed over the project's counted milestones."""
    row = conn.execute(
        "SELECT COALESCE(sum(m.allocated_hours), 0) AS hours, COALESCE(sum(m.budget_amount), 0) AS budget "
        "FROM milestones m WHERE m.project_id = %s AND (m.archived_at IS NULL OR m.status = 'completed') "
        "AND (%s::uuid IS NULL OR m.id <> %s)",
        (project_id, exclude_id, exclude_id),
    ).fetchone()
    return {"hours": float(row["hours"]), "budget": float(row["budget"])} if row else {"hours": 0.0, "budget": 0.0}


def bounds(conn: psycopg.Connection[Any], project_id: uuid.UUID) -> dict[str, Any]:
    """Earliest start and latest due date among a project's counted milestones."""
    row = conn.execute(
        "SELECT min(m.start_date) AS first_start, max(m.due_date) AS last_due FROM milestones m "
        "WHERE m.project_id = %s AND (m.archived_at IS NULL OR m.status = 'completed')",
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
    budget_amount: float,
) -> uuid.UUID:
    """Create a milestone and return its id."""
    row = conn.execute(
        """
        INSERT INTO milestones (project_id, name, description, start_date, due_date, allocated_hours, budget_amount)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (project_id, name, description, start_date, due_date, allocated_hours, budget_amount),
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


def complete(conn: psycopg.Connection[Any], milestone_id: uuid.UUID, *, reviewer_id: uuid.UUID, note: str) -> None:
    """Mark a milestone completed after review; completed milestones are archived (admin-visible only)."""
    conn.execute(
        "UPDATE milestones SET status = 'completed', completed_at = now(), archived_at = now(), "
        "reviewed_by = %s, review_note = %s WHERE id = %s",
        (reviewer_id, note, milestone_id),
    )


def archive(conn: psycopg.Connection[Any], milestone_id: uuid.UUID) -> None:
    """Cancel a milestone without completing it (archived, never deleted)."""
    conn.execute("UPDATE milestones SET archived_at = now() WHERE id = %s", (milestone_id,))
